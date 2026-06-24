# -*- coding: utf-8 -*-
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))

from c2gauss_v32.v32_field_trace import FieldTraceEngine


def test_cfg_and_srelebook_chain():
    cfg = '''
tr_book_no "trim(:TR_BOOK_NO)",
tr_tran_amt "trim(:TR_TRAN_AMT)",
remark "trim(:REMARK)",
'''
    c = '''
memcpy(SReleBook.book_no, SAmwkpl06.tr_book_no + 2, 8);
SReleBook.tran_amt = atof(pSamwkpl06->tr_tran_amt);
strcpy(SReleBook.remark, SAmwkpl06.remark);
g_Trim(SReleBook.remark);
'''
    e = FieldTraceEngine()
    e.build_cfg_map(cfg)
    e.record_source(c, 10)
    stmt = 'EXEC SQL EXECUTE INS_RELEBOOK USING :SReleBook.book_no, :SReleBook.tran_amt, :SReleBook.remark;'
    assigns = e.prepare_before_insert_for_execute(stmt, 'EVDAT_CXRELEBOOK')
    assert 'V_SRELEBOOK_BOOK_NO := substring(R.tr_book_no FROM 3 FOR 8);' in assigns
    assert "V_SRELEBOOK_TRAN_AMT := CAST(NULLIF(trim(R.tr_tran_amt), '') AS NUMERIC);" in assigns
    assert 'V_SRELEBOOK_REMARK := trim(R.remark);' in assigns
    replaced = e.replace_srelebook_using_vars(stmt)
    assert ':SReleBook.' not in replaced
    assert 'V_SRELEBOOK_BOOK_NO' in replaced


def test_unresolved_goes_to_review_not_drop():
    e = FieldTraceEngine()
    e.build_cfg_map('known "trim(:KNOWN)",')
    stmt = 'EXEC SQL EXECUTE INS_RELEBOOK USING :SReleBook.unknown_field;'
    assigns = e.prepare_before_insert_for_execute(stmt, 'EVHIS_CXRELEBOOKHIS')
    assert 'V_SRELEBOOK_UNKNOWN_FIELD := NULL;' in assigns
    md = e.review.to_markdown()
    assert 'SReleBook.unknown_field' in md
    assert 'EVHIS_CXRELEBOOKHIS' in md


def test_strncpy_without_offset():
    e = FieldTraceEngine()
    e.build_cfg_map('abc "trim(:ABC)",')
    e.record_line('strncpy(SReleBook.short_abc, SAmwkpl06.abc, 4);', 88)
    assigns = e.emit_srelebook_assignments(['short_abc'], 'EVDAT_CXRELEBOOK')
    assert 'substring(R.abc FROM 1 FOR 4)' in assigns


def test_atoi():
    e = FieldTraceEngine()
    e.build_cfg_map('cnt "trim(:CNT)",')
    e.record_line('SReleBook.cnt = atoi(SAmwkpl06.cnt);', 89)
    assigns = e.emit_srelebook_assignments(['cnt'], 'EVDAT_CXRELEBOOK')
    assert "CAST(NULLIF(trim(R.cnt), '') AS INTEGER)" in assigns
