# 钙钛矿正文与SI联合抽取

运行入口不变：`python ragflows/main.py`。`EXTRACTION_TASK = 'perovskite'` 启用新任务。

## 输入与配置

- `ragflows/configs.py` 的 `DOC_DIR`：PDF文件夹。每组必须有 `516.pdf` 和 `516-SI.pdf`；大小写不敏感。按编号从大到小处理。缺文件或编号重复在上传前报错。
- `PEROVSKITE_XLSX_PATH`：A列文献编号id，B列材料名称catalyst。留空沿用原 `NANOZYME_XLSX_PATH`。同一编号可以有多行材料名称；空A列沿用上一编号。
- `CHAT_ID`、`DIFY_DOC_KB_ID`、`OPENAI_BASE_URL` 和API密钥仍使用现有配置。请在这个RAGFlow对话中选择钙钛矿任务使用的模型和知识库，并去除仅适用于纳米酶的系统提示词。
- `PEROVSKITE_OUTPUT_DIR`：新结果目录，默认 `/public/ly/hj/ragflow-data-perovskite`。
- `DELETE_FROM_DATABASE = True`：结果保存后清理两份远程文档及向量切片；不删除本地PDF。
- `ONLY_UPLOAD = False`：执行解析和抽取。True时只上传两份PDF，不抽取、不删除。
- `PEROVSKITE_MAX_CONTEXT_CHARS`：正文+SI文本上限，默认120000字符（不是token数）。超过时停止保留文档；不会静默丢弃SI或截断全文。需结合所选模型上下文容量调整。

## 流程与输出

先上传/复用正文和SI，等待两份解析完成，再读取两份全部切片。每个材料调用同一个RAGFlow对话，最后一条问题传入两个doc_ids，并在消息中提供两份来源证据。

输出CSV列顺序：

`id,catalyst,PCE (%),VOC (V),JSC (mA cm-2),FF (%),buried interface passivation agent,perovskite layer additives,perovskite interface passivation agent`

模型返回全部7个参数键；未报告的参数为null，CSV写作字面值`null`。电学值必须为数字。三种试剂按处理位置区别，要求输出已报告的化学式/通用化学缩写，多个用逗号分隔（CSV自动引号转义）。一行只对应同一材料的同一器件条件，优先文献明确标注的冠军器件，不能拼接不同器件的最大值。

部分材料输出无效时重试，仍失败则只跳过该材料。成功行保存CSV；每组额外保存JSON，包含来源文档ID、成功结果及失败原因/最后一次响应。全部失败或XLSX无名称也保存JSON记录，再清理本组。

接口异常、解析失败、保存失败保留当前组并停止。删除在一次API请求中提交两个ID，但不是数据库事务；其中一份未删干净会停止，重启后先继续清理剩余文档。

进度文件位于输出目录 `.perovskite_progress_<知识库ID>_<对话ID>.json`。成功保存结果后才登记待清理状态，确认两份清理完成后才登记已完成。重启跳过已完成编号，不使用旧的单PDF序号。需要重跑已完成组时，先备份该进度文件，再移除对应completed编号（不要改pending记录）。

RAGFlow服务端必须支持当前版本OpenAI兼容对话接口中的doc_ids；客户端会发送两个ID，但服务端是否遵守范围仍需在部署环境验证。所有来源文本显式传入模型，实际准确性仍依赖PDF解析、模型能力及对话设置。
