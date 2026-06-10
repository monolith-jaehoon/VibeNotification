# 贡献指南

感谢您考虑为 VibeNotification 项目做出贡献！本指南将帮助您了解如何参与项目开发。

## 🎯 开发流程

### 1. 设置开发环境

```bash
# 1. Fork 项目
# 2. 克隆您的 fork
git clone https://github.com/yourusername/VibeNotification.git
cd VibeNotification

# 3. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或
venv\Scripts\activate     # Windows

# 4. 安装开发依赖
pip install -e ".[dev]"
```

### 2. 创建分支

```bash
# 从 main 分支创建功能分支
git checkout -b feature/your-feature-name

# 或修复 bug 的分支
git checkout -b fix/issue-description
```

### 3. 进行更改

- 编写代码
- 添加测试
- 更新文档
- 确保代码通过所有检查

### 4. 提交更改

```bash
# 添加更改
git add .

# 提交（使用 Conventional Commits 格式）
git commit -m "feat: 添加新功能"
# 或
git commit -m "fix: 修复某个问题"
# 或
git commit -m "docs: 更新文档"
```

### 5. 推送到远程

```bash
git push origin feature/your-feature-name
```

### 6. 创建 Pull Request

在 GitHub 上创建 Pull Request，描述您的更改。

## 📝 代码规范

### 代码风格

我们使用以下工具确保代码质量：

```bash
# 格式化代码
black vibe_notification/ tests/
isort vibe_notification/ tests/

# 检查代码质量
flake8 vibe_notification/ tests/
mypy vibe_notification/
```

### 提交信息格式

使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

- `feat:` 新功能
- `fix:` bug 修复
- `docs:` 文档更新
- `style:` 代码格式（不影响功能）
- `refactor:` 代码重构
- `test:` 测试相关
- `chore:` 构建过程或辅助工具

示例：
```
feat: 添加 Windows 通知支持
fix: 修复 Linux 声音播放问题
docs: 更新安装说明
```

### 测试要求

- 新功能必须包含测试
- 修复 bug 时添加回归测试
- 确保所有测试通过

```bash
# 运行测试
pytest tests/

# 带覆盖率
pytest --cov=vibe_notification tests/
```

## 🐛 报告问题

### Bug 报告

1. 检查是否已有相关 issue
2. 创建新 issue，包含：
   - 清晰的问题描述
   - 复现步骤
   - 期望行为
   - 实际行为
   - 环境信息（系统、Python 版本等）
   - 错误日志

### 功能请求

1. 检查是否已有相关讨论
2. 创建新 issue，包含：
   - 功能描述
   - 使用场景
   - 可能的实现方案
   - 相关参考

## 🏗️ 项目结构

```
VibeNotification/
├── vibe_notification/      # 核心包
│   ├── cli.py              # CLI 入口
│   ├── core.py             # 主协调器
│   ├── parsers/            # Claude Code / Codex 事件解析
│   ├── notifiers/          # 声音和系统通知器
│   └── adapters.py         # 跨平台命令适配
├── tests/                  # 测试代码
├── docs/                   # 文档
├── examples/               # 示例代码
├── pyproject.toml          # 构建、依赖和工具元数据
└── config.example.json     # 配置示例
```

## 🔧 开发工具

### 推荐的 IDE 设置

**VS Code:**
```json
{
  "python.formatting.provider": "black",
  "python.formatting.blackArgs": ["--line-length", "88"],
  "python.sortImports.args": ["--profile", "black"],
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {
    "source.organizeImports": true
  }
}
```

**PyCharm:**
- 启用 Black 和 isort 插件
- 配置自动格式化

### 调试

```python
# 在代码中添加调试日志
import logging
logger = logging.getLogger(__name__)
logger.debug("调试信息")
```

## 📚 文档

### 更新文档

- README.md: 项目概述和快速开始
- docs/: 详细文档
- 代码中的 docstring

### 文档格式

- 使用 Markdown 格式
- 代码示例使用正确的语言标记
- 保持链接有效

## 🤝 行为准则

### 我们的承诺

我们致力于为所有贡献者提供友好、尊重的环境。

### 我们的标准

- 使用友好和包容的语言
- 尊重不同的观点和经验
- 优雅地接受建设性批评
- 关注对社区最有利的事情
- 对其他社区成员表示同理心

### 不可接受的行为

- 使用性化语言或图像
- 挑衅、侮辱/贬损评论
- 公开或私下骚扰
- 未经明确许可发布他人的私人信息
- 其他在专业环境中不适当的行为

## 📄 许可证

通过贡献代码，您同意您的贡献将在项目的 MIT 许可证下授权。

## 🙏 感谢

感谢所有贡献者！您的参与使这个项目变得更好。

---

有问题？请在 issue 中讨论或联系维护者。
