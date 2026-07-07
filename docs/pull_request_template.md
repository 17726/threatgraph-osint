<!-- 提交 PR 前请先阅读 CONTRIBUTING.md 中的 MR / Pull Request 要求 -->

### 本次改了什么

<!-- 描述改动内容，前端页面改动建议附截图，后端接口改动建议贴接口返回示例 -->

### 为什么要改

<!-- 说明改动原因 -->

### 怎么验证

<!-- 说明本地运行了哪些验证命令 -->

<!-- 将 [ ] 改为 [x] 表示确认 -->
- [ ] 后端测试通过：`docker compose run --rm backend python -m pytest backend/tests -v`
- [ ] 前端测试通过：`npm --prefix frontend run test`
- [ ] 前端构建通过：`npm --prefix frontend run build`
- [ ] 前端格式化通过：`npm --prefix frontend run format:check`

### 是否影响 API 契约或数据契约

<!-- 将 [ ] 改为 [x] 表示确认 -->
- [ ] 是（已在对应 docs 文件中更新，并提醒架构与数据规范组评审）
- [ ] 否
