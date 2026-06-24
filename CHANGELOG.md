# CHANGELOG V32

## 新增

1. 新增 `FieldTraceEngine`，用于统一维护 cfg、结构体字段、SReleBook 字段链路。
2. 新增 `ReviewCollector`，未解析字段集中写入 review。
3. 新增 `memcpy / strncpy / strcpy / g_Trim / atoi / atof` 转 SQL 表达式支持。
4. 新增 C 字符串偏移到 SQL substring 的 `+1` 转换。
5. 新增 `EXECUTE INS_RELEBOOK USING :SReleBook.xxx` 到 `V_SRELEBOOK_XXX` 的替换。
6. 新增 `INSERT` 前赋值语句生成。

## 保留

1. V31 混合占位符修复接口保留：`normalize_mixed_placeholders()`。
2. 未改动中间表模式、静态游标删除、T_LOG.LOG 现有逻辑。

## 禁止回退

1. 找不到来源字段不允许丢 INSERT。
2. `EVDAT_CXRELEBOOK` / `EVHIS_CXRELEBOOKHIS` 两个 INSERT 必须保留。
3. `review.md` 必须记录未解析字段。
