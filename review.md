# V32 review.md 模板

## V32 未解析字段

- 无。

## V32 检查项

- [ ] `grep -ni "INSERT INTO EVDAT_CXRELEBOOK" output/*.sql` 能搜到结果。
- [ ] `grep -ni "INSERT INTO EVHIS_CXRELEBOOKHIS" output/*.sql` 能搜到结果。
- [ ] `grep -ni "V_SRELEBOOK_" output/*.sql` 能搜到结果。
- [ ] `INSERT VALUES` 中不再出现 `SReleBook.xxx`。
- [ ] 未解析字段集中记录在本文件，不静默丢弃。
- [ ] V31 混合占位符修复仍保留。
- [ ] 中间表模式仍保留：`FOR R IN SELECT * FROM 中间表 LOOP`。
- [ ] 静态游标通用删除逻辑仍保留。
- [ ] `T_LOG.LOG` 仍保留。
- [ ] README、独立 ZIP、Word 内嵌 ZIP 均生成。
