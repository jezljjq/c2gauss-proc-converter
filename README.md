# c2gauss-proc-converter

C 转高斯存储过程转换工具。

当前版本先提交 V32 字段链追踪补丁模块，用于修复中间表模式下 `SReleBook.xxx` 来源追踪和 `INS_RELEBOOK` 插入生成问题。

## V32 重点

- 建立 `cfg 字段 -> R.字段` 映射。
- 建立 `SAmwkpl06.xxx / pSamwkpl06->xxx -> R.字段` 映射。
- 支持 `SReleBook.xxx` 赋值链追踪。
- 支持 `memcpy / strncpy / strcpy / g_Trim / atoi / atof / substring` 偏移转换。
- `EXECUTE INS_RELEBOOK USING :SReleBook.xxx` 转成 `V_SRELEBOOK_XXX`。
- 在 `INSERT` 前生成 `V_SRELEBOOK_XXX := ...` 赋值逻辑。
- 找不到来源字段时写入 `review.md`，不直接丢弃 INSERT。
- 继续保留 V31 混合占位符修复、中间表模式、静态游标通用删除、`T_LOG.LOG`、README、Word 内嵌 ZIP 要求。

## 目录结构

```text
c2gauss-proc-converter/
├─ README.md
├─ CHANGELOG.md
├─ review.md
├─ src/
│  └─ c2gauss_v32/
│     ├─ __init__.py
│     └─ v32_field_trace.py
├─ tests/
│  └─ test_v32_field_trace.py
├─ scripts/
│  └─ run_v32_smoke.py
├─ examples/
│  └─ input/
│     ├─ loader.cfg
│     └─ amwkpl06_sample.c
└─ dist/
   └─ README.md
```

## 快速验证

```bash
python scripts/run_v32_smoke.py
python -m pytest -q
```

## 接入现有转换工具

核心类：

```python
from c2gauss_v32.v32_field_trace import FieldTraceEngine

trace = FieldTraceEngine(middle_alias='R')
trace.build_cfg_map(loader_cfg_text)
trace.record_source(c_source_text, start_line_no=1)

assign_sql = trace.prepare_before_insert_for_execute(execute_stmt, 'EVDAT_CXRELEBOOK')
new_execute_stmt = trace.replace_srelebook_using_vars(execute_stmt)
review_text = trace.review.to_markdown()
```

## V32 验收命令

```bash
grep -ni "INSERT INTO EVDAT_CXRELEBOOK" output/*.sql
grep -ni "INSERT INTO EVHIS_CXRELEBOOKHIS" output/*.sql
grep -ni "V_SRELEBOOK_" output/*.sql
grep -ni "SReleBook\." output/*.sql
grep -ni "V32 未解析字段" review.md
```
