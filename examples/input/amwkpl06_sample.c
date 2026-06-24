memcpy(SReleBook.book_no, SAmwkpl06.tr_book_no + 2, 8);
SReleBook.tran_amt = atof(pSamwkpl06->tr_tran_amt);
strcpy(SReleBook.remark, SAmwkpl06.remark);
g_Trim(SReleBook.remark);
EXEC SQL EXECUTE INS_RELEBOOK USING :SReleBook.book_no, :SReleBook.tran_amt, :SReleBook.remark, :SReleBook.no_src;
