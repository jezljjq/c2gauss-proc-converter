# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))

from c2gauss_v32.v32_field_trace import FieldTraceEngine

cfg = '''
tr_book_no "trim(:TR_BOOK_NO)",
tr_tran_amt "trim(:TR_TRAN_AMT)",
remark "trim(:REMARK)",
'''

c_src = '''
memcpy(SReleBook.book_no, SAmwkpl06.tr_book_no + 2, 8);
SReleBook.tran_amt = atof(pSamwkpl06->tr_tran_amt);
strcpy(SReleBook.remark, SAmwkpl06.remark);
g_Trim(SReleBook.remark);
'''

execute_stmt = 'EXEC SQL EXECUTE INS_RELEBOOK USING :SReleBook.book_no, :SReleBook.tran_amt, :SReleBook.remark, :SReleBook.no_src;'

engine = FieldTraceEngine()
engine.build_cfg_map(cfg)
engine.record_source(c_src, 100)

print('-- C line 100-103')
print(engine.prepare_before_insert_for_execute(execute_stmt, 'EVDAT_CXRELEBOOK'))
print('')
print('INSERT INTO EVDAT_CXRELEBOOK (...) VALUES (...);')
print(engine.replace_srelebook_using_vars(execute_stmt))
print('')
print(engine.review.to_markdown())
