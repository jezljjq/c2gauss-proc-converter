# -*- coding: utf-8 -*-
"""
V32 field tracing helper for C -> Gauss stored procedure converter.

Python 2.7 compatible on purpose.

Main responsibilities:
1. Build loader cfg field -> R.field mapping.
2. Build SAmwkpl06.xxx / pSamwkpl06->xxx -> R.field or expression mapping.
3. Trace SReleBook.xxx assignment chain.
4. Convert memcpy / strncpy / strcpy / g_Trim / atoi / atof / substring offset.
5. Replace EXECUTE INS_RELEBOOK USING :SReleBook.xxx with V_SRELEBOOK_XXX.
6. Emit V_SRELEBOOK_XXX assignments before INSERT.
7. Never drop INSERT when source cannot be resolved; emit NULL TODO and review entries.

This module is intentionally small and dependency-free so it can be merged into the
existing converter without pulling in extra packages.
"""
from __future__ import print_function

import re

try:
    basestring
except NameError:  # py3 test runtime
    basestring = str


_IDENT = r'[A-Za-z_][A-Za-z0-9_]*'


def _strip(s):
    if s is None:
        return ''
    return s.strip()


def _lower(s):
    return _strip(s).lower()


def _upper_field(s):
    return re.sub(r'[^A-Za-z0-9_]', '_', _strip(s)).upper()


def split_c_args(text):
    """Split a C function argument list while respecting nested parentheses and quotes."""
    args = []
    buf = []
    depth = 0
    quote = None
    escape = False
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            buf.append(ch)
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == quote:
                quote = None
        else:
            if ch in ('"', "'"):
                quote = ch
                buf.append(ch)
            elif ch == '(':
                depth += 1
                buf.append(ch)
            elif ch == ')':
                if depth > 0:
                    depth -= 1
                buf.append(ch)
            elif ch == ',' and depth == 0:
                args.append(''.join(buf).strip())
                buf = []
            else:
                buf.append(ch)
        i += 1
    tail = ''.join(buf).strip()
    if tail:
        args.append(tail)
    return args


def remove_outer_parens(expr):
    expr = _strip(expr)
    while expr.startswith('(') and expr.endswith(')'):
        depth = 0
        ok = True
        quote = None
        for i, ch in enumerate(expr):
            if quote:
                if ch == quote:
                    quote = None
                elif ch == '\\':
                    # skip next char in a simple way
                    pass
            else:
                if ch in ('"', "'"):
                    quote = ch
                elif ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                    if depth == 0 and i != len(expr) - 1:
                        ok = False
                        break
        if ok:
            expr = expr[1:-1].strip()
        else:
            break
    return expr


def strip_c_cast(expr):
    """Remove simple leading C casts: (char *)x, (double)x, (long)x."""
    expr = remove_outer_parens(expr)
    cast_re = re.compile(r'^\(\s*(?:const\s+)?(?:struct\s+)?[A-Za-z_][A-Za-z0-9_\s\*]*\s*\)\s*(.+)$')
    m = cast_re.match(expr)
    while m:
        expr = remove_outer_parens(m.group(1))
        m = cast_re.match(expr)
    return expr


class ReviewCollector(object):
    def __init__(self):
        self.items = []

    def add_unresolved(self, field_ref, target_table, context, reason, c_line=None):
        item = {
            'field_ref': field_ref,
            'target_table': target_table or '',
            'context': context or '',
            'reason': reason or '',
            'c_line': c_line or '',
        }
        # Avoid duplicate noise.
        key = (item['field_ref'], item['target_table'], item['context'], item['reason'], item['c_line'])
        for old in self.items:
            old_key = (old['field_ref'], old['target_table'], old['context'], old['reason'], old['c_line'])
            if old_key == key:
                return
        self.items.append(item)

    def to_markdown(self):
        lines = []
        lines.append('## V32 未解析字段')
        lines.append('')
        if not self.items:
            lines.append('- 无。')
            lines.append('')
            return '\n'.join(lines)
        for item in self.items:
            lines.append('### %s' % item['field_ref'])
            lines.append('')
            if item['c_line']:
                lines.append('- C 行号：%s' % item['c_line'])
            if item['context']:
                lines.append('- 使用位置：%s' % item['context'])
            if item['target_table']:
                lines.append('- 目标表：%s' % item['target_table'])
            if item['reason']:
                lines.append('- 问题：%s' % item['reason'])
            lines.append('- 建议：人工确认该字段来源，或补充 cfg/结构体赋值链转换规则。')
            lines.append('')
        return '\n'.join(lines)


class FieldTraceEngine(object):
    """Trace fields from middle table alias R to SReleBook variables."""

    def __init__(self, middle_alias='R'):
        self.middle_alias = middle_alias or 'R'
        self.cfg_map = {}       # lower cfg field -> R.field
        self.ref_map = {}       # normalized C ref -> SQL expression
        self.srelebook_map = {} # lower field -> SQL expression
        self.srelebook_c_line = {}
        self.review = ReviewCollector()

    # ------------------------- cfg -------------------------
    def build_cfg_map(self, cfg_text):
        """Build cfg field -> R.field mapping from loader cfg text."""
        if not cfg_text:
            return self.cfg_map
        # Supports: rt_ctl1 "trim(:RT_CTL1)",  or  rt_ctl1 position(...)
        field_re = re.compile(r'^\s*(' + _IDENT + r')\b', re.I)
        for raw in cfg_text.splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or line.startswith('--'):
                continue
            m = field_re.match(line)
            if not m:
                continue
            field = m.group(1)
            key = _lower(field)
            self.cfg_map[key] = '%s.%s' % (self.middle_alias, key)
        # Default struct fields can be resolved directly through cfg name.
        for key, expr in self.cfg_map.items():
            self.ref_map['samwkpl06.%s' % key] = expr
            self.ref_map['psamwkpl06->%s' % key] = expr
        return self.cfg_map

    # ---------------------- ref helpers --------------------
    def normalize_c_ref(self, ref):
        ref = _strip(ref)
        ref = strip_c_cast(ref)
        ref = ref.replace(' ', '')
        ref = ref.replace('->', '->')
        return ref.lower()

    def srelebook_var_name(self, field):
        return 'V_SRELEBOOK_%s' % _upper_field(field)

    def is_srelebook_ref(self, ref):
        return re.match(r'^SReleBook\.(' + _IDENT + r')$', _strip(ref), re.I) is not None

    def get_srelebook_field(self, ref):
        m = re.match(r'^SReleBook\.(' + _IDENT + r')$', _strip(ref), re.I)
        if m:
            return m.group(1)
        return None

    def source_ref_to_sql(self, ref, target_table='', context='', c_line=''):
        """Resolve a C reference/expression to SQL, or None if unresolved."""
        ref = _strip(ref)
        if not ref:
            return None
        ref = strip_c_cast(ref)

        # Character address: &SReleBook.xxx, &SAmwkpl06.xxx
        if ref.startswith('&'):
            ref = ref[1:].strip()

        # String literal / numeric literal pass-through.
        if (len(ref) >= 2 and ref[0] in ('"', "'") and ref[-1] == ref[0]):
            return ref
        if re.match(r'^[-+]?\d+(?:\.\d+)?$', ref):
            return ref
        if re.match(r'^NULL$', ref, re.I):
            return 'NULL'

        # SReleBook.xxx means use materialized variable.
        f = self.get_srelebook_field(ref)
        if f:
            return self.srelebook_var_name(f)

        # Direct cfg field name.
        key = _lower(ref)
        if key in self.cfg_map:
            return self.cfg_map[key]

        # SAmwkpl06.xxx / pSamwkpl06->xxx.
        m = re.match(r'^(SAmwkpl06)\.(' + _IDENT + r')$', ref, re.I)
        if m:
            field_key = _lower(m.group(2))
            norm = 'samwkpl06.%s' % field_key
            if norm in self.ref_map:
                return self.ref_map[norm]
            if field_key in self.cfg_map:
                return self.cfg_map[field_key]
            return None
        m = re.match(r'^(pSamwkpl06)->(' + _IDENT + r')$', ref, re.I)
        if m:
            field_key = _lower(m.group(2))
            norm = 'psamwkpl06->%s' % field_key
            if norm in self.ref_map:
                return self.ref_map[norm]
            if field_key in self.cfg_map:
                return self.cfg_map[field_key]
            return None

        # Known generated local variable mapping.
        norm = self.normalize_c_ref(ref)
        if norm in self.ref_map:
            return self.ref_map[norm]

        return None

    def parse_offset_expr(self, expr):
        """Return (base_expr, offset_int_or_text) for C expression like src + 2."""
        expr = strip_c_cast(expr)
        # Only peel the last simple + offset used by memcpy/strncpy source.
        m = re.match(r'^(.+?)\s*\+\s*(\d+)\s*$', expr)
        if m:
            return m.group(1).strip(), int(m.group(2))
        return expr, 0

    def slice_sql(self, src_expr, length_expr, target_table='', context='', c_line=''):
        base, off = self.parse_offset_expr(src_expr)
        sql_base = self.source_ref_to_sql(base, target_table, context, c_line)
        if not sql_base:
            return None
        start = off + 1
        length_expr = _strip(length_expr)
        return 'substring(%s FROM %s FOR %s)' % (sql_base, start, length_expr)

    def expr_to_sql(self, expr, target_table='', context='', c_line=''):
        expr = _strip(expr)
        expr = expr.rstrip(';').strip()
        expr = strip_c_cast(expr)

        # atoi(src)
        m = re.match(r'^atoi\s*\((.*)\)$', expr, re.I)
        if m:
            args = split_c_args(m.group(1))
            src = self.expr_to_sql(args[0], target_table, context, c_line) if args else None
            if not src:
                return None
            return "CAST(NULLIF(trim(%s), '') AS INTEGER)" % src

        # atof(src)
        m = re.match(r'^atof\s*\((.*)\)$', expr, re.I)
        if m:
            args = split_c_args(m.group(1))
            src = self.expr_to_sql(args[0], target_table, context, c_line) if args else None
            if not src:
                return None
            return "CAST(NULLIF(trim(%s), '') AS NUMERIC)" % src

        # g_Trim(src) used as expression.
        m = re.match(r'^g_Trim\s*\((.*)\)$', expr, re.I)
        if m:
            args = split_c_args(m.group(1))
            src = self.expr_to_sql(args[0], target_table, context, c_line) if args else None
            if not src:
                return None
            return 'trim(%s)' % src

        # C substring by pointer offset without explicit length cannot be safely sliced.
        base, off = self.parse_offset_expr(expr)
        if off:
            sql_base = self.source_ref_to_sql(base, target_table, context, c_line)
            if sql_base:
                return 'substring(%s FROM %s)' % (sql_base, off + 1)

        sql_ref = self.source_ref_to_sql(expr, target_table, context, c_line)
        if sql_ref:
            return sql_ref

        # Simple concatenation handling: a + b is often numeric in C, but for string build
        # existing converter may already handle strcat/sprintf. Keep unresolved here rather
        # than guessing incorrectly.
        return None

    # ---------------------- assignment tracing ----------------------
    def assign_to_ref(self, dest, sql_expr, c_line=''):
        dest = _strip(dest)
        if dest.startswith('&'):
            dest = dest[1:].strip()
        f = self.get_srelebook_field(dest)
        if f:
            key = _lower(f)
            self.srelebook_map[key] = sql_expr
            self.srelebook_c_line[key] = c_line or self.srelebook_c_line.get(key, '')
            return True

        m = re.match(r'^SAmwkpl06\.(' + _IDENT + r')$', dest, re.I)
        if m:
            key = _lower(m.group(1))
            self.ref_map['samwkpl06.%s' % key] = sql_expr
            return True
        m = re.match(r'^pSamwkpl06->(' + _IDENT + r')$', dest, re.I)
        if m:
            key = _lower(m.group(1))
            self.ref_map['psamwkpl06->%s' % key] = sql_expr
            return True

        norm = self.normalize_c_ref(dest)
        if norm:
            self.ref_map[norm] = sql_expr
            return True
        return False

    def record_line(self, line, line_no=None):
        """Record one C source line. Returns True if a relevant conversion was captured."""
        raw = line
        line = _strip(line)
        if not line:
            return False
        c_line = str(line_no) if line_no is not None else ''

        # memcpy(dest, src [+ offset], len)
        m = re.search(r'\bmemcpy\s*\((.*)\)\s*;', line, re.I)
        if m:
            args = split_c_args(m.group(1))
            if len(args) >= 3:
                dest, src, length = args[0], args[1], args[2]
                sql = self.slice_sql(src, length, context='memcpy', c_line=c_line)
                if sql:
                    return self.assign_to_ref(dest, sql, c_line)
            return False

        # strncpy(dest, src [+ offset], len)
        m = re.search(r'\bstrncpy\s*\((.*)\)\s*;', line, re.I)
        if m:
            args = split_c_args(m.group(1))
            if len(args) >= 3:
                dest, src, length = args[0], args[1], args[2]
                sql = self.slice_sql(src, length, context='strncpy', c_line=c_line)
                if sql:
                    return self.assign_to_ref(dest, sql, c_line)
            return False

        # strcpy(dest, src)
        m = re.search(r'\bstrcpy\s*\((.*)\)\s*;', line, re.I)
        if m:
            args = split_c_args(m.group(1))
            if len(args) >= 2:
                dest, src = args[0], args[1]
                sql = self.expr_to_sql(src, context='strcpy', c_line=c_line)
                if sql:
                    return self.assign_to_ref(dest, sql, c_line)
            return False

        # g_Trim(dest); in-place trim.  For SReleBook.xxx we must trim the
        # already traced source expression, not the generated V_SRELEBOOK_XXX name.
        m = re.search(r'\bg_Trim\s*\((.*)\)\s*;', line, re.I)
        if m:
            args = split_c_args(m.group(1))
            if args:
                dest = args[0]
                f = self.get_srelebook_field(dest)
                if f and _lower(f) in self.srelebook_map:
                    old_sql = self.srelebook_map[_lower(f)]
                else:
                    old_sql = self.expr_to_sql(dest, context='g_Trim', c_line=c_line)
                if old_sql:
                    return self.assign_to_ref(dest, 'trim(%s)' % old_sql, c_line)
            return False

        # Assignment: dest = expr; excluding comparisons.
        m = re.match(r'^(.+?)\s*=\s*(.+?)\s*;\s*$', line)
        if m and not re.search(r'(==|!=|<=|>=)', line):
            dest = m.group(1).strip()
            expr = m.group(2).strip()
            sql = self.expr_to_sql(expr, context='assignment', c_line=c_line)
            if sql:
                return self.assign_to_ref(dest, sql, c_line)
            return False

        return False

    def record_source(self, c_text, start_line_no=1):
        if not c_text:
            return
        for idx, line in enumerate(c_text.splitlines()):
            self.record_line(line, start_line_no + idx)

    # ---------------------- insert materialization ----------------------
    def resolve_srelebook_field(self, field, target_table='', context=''):
        key = _lower(field)
        if key in self.srelebook_map:
            return self.srelebook_map[key]
        # Fallback: sometimes SReleBook.xxx maps directly to cfg field xxx.
        if key in self.cfg_map:
            return self.cfg_map[key]
        self.review.add_unresolved('SReleBook.%s' % field, target_table, context,
                                   '未能追踪到 cfg / R 字段来源', self.srelebook_c_line.get(key, ''))
        return None

    def emit_srelebook_assignments(self, fields, target_table='', context='EXECUTE INS_RELEBOOK USING', indent='    '):
        """Emit V_SRELEBOOK_XXX := ... lines before INSERT."""
        lines = []
        seen = set()
        for field in fields:
            key = _lower(field)
            if key in seen:
                continue
            seen.add(key)
            var_name = self.srelebook_var_name(field)
            expr = self.resolve_srelebook_field(field, target_table, context)
            if expr:
                lines.append('%s%s := %s;' % (indent, var_name, expr))
            else:
                lines.append('%s%s := NULL; -- TODO V32: 未找到来源字段，详见 review.md' % (indent, var_name))
        return '\n'.join(lines)

    def extract_srelebook_fields_from_using(self, execute_stmt):
        fields = []
        for m in re.finditer(r':\s*SReleBook\.(' + _IDENT + r')', execute_stmt, re.I):
            fields.append(m.group(1))
        return fields

    def replace_srelebook_using_vars(self, execute_stmt):
        def repl(m):
            return self.srelebook_var_name(m.group(1))
        return re.sub(r':\s*SReleBook\.(' + _IDENT + r')', repl, execute_stmt, flags=re.I)

    def prepare_before_insert_for_execute(self, execute_stmt, target_table):
        fields = self.extract_srelebook_fields_from_using(execute_stmt)
        return self.emit_srelebook_assignments(fields, target_table,
                                               'EXECUTE INS_RELEBOOK USING')

    # ---------------------- V31 mixed placeholder guard ----------------------
    def normalize_mixed_placeholders(self, sql_text, using_vars):
        """Keep V31 behavior: normalize dynamic SQL placeholders without losing USING order.

        Existing converter can keep its own implementation. This fallback turns colon refs
        into ? and appends missing refs to using_vars. It does not alter literal strings.
        """
        using_vars = list(using_vars or [])
        out = []
        buf = []
        quote = None
        i = 0
        while i < len(sql_text):
            ch = sql_text[i]
            if quote:
                buf.append(ch)
                if ch == quote:
                    quote = None
                i += 1
                continue
            if ch in ('"', "'"):
                quote = ch
                buf.append(ch)
                i += 1
                continue
            if ch == ':':
                m = re.match(r':\s*(' + _IDENT + r'(?:\.' + _IDENT + r'|->' + _IDENT + r')?)', sql_text[i:], re.I)
                if m:
                    ref = m.group(1).replace(' ', '')
                    using_vars.append(ref)
                    buf.append('?')
                    i += len(m.group(0))
                    continue
            buf.append(ch)
            i += 1
        out_sql = ''.join(buf)
        return out_sql, using_vars


if __name__ == '__main__':
    cfg = '''\ntr_book_no "trim(:TR_BOOK_NO)",\ntr_tran_amt "trim(:TR_TRAN_AMT)",\nremark "trim(:REMARK)",\n'''
    c = '''\nmemcpy(SReleBook.book_no, SAmwkpl06.tr_book_no + 2, 8);\nSReleBook.tran_amt = atof(pSamwkpl06->tr_tran_amt);\nstrcpy(SReleBook.remark, SAmwkpl06.remark);\ng_Trim(SReleBook.remark);\n'''
    e = FieldTraceEngine()
    e.build_cfg_map(cfg)
    e.record_source(c, 100)
    stmt = 'EXEC SQL EXECUTE INS_RELEBOOK USING :SReleBook.book_no, :SReleBook.tran_amt, :SReleBook.remark, :SReleBook.no_src;'
    print(e.prepare_before_insert_for_execute(stmt, 'EVDAT_CXRELEBOOK'))
    print(e.replace_srelebook_using_vars(stmt))
    print(e.review.to_markdown())
