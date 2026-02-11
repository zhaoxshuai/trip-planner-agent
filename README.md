# 个人智能旅行助手

一个基于多智能体系统的AI旅行规划平台，能够根据用户需求自动生成详细的旅行计划。

## 项目结构

```
trip-planner-agent/
├── backend/                    # 后端代码
│   ├── app/
│   │   ├── agents/            # 智能体实现
│   │   ├── api/               # API路由
│   │   ├── core/              # 核心模块
│   │   ├── models/            # 数据模型
│   │   ├── services/          # 服务层
│   │   ├── tools/             # 工具模块
│   │   └── config.py          # 配置文件
│   └── requirements.txt       # Python依赖
│
└── frontend/                   # 前端代码
    ├── src/
    │   ├── views/             # 页面组件
    │   ├── services/          # API服务
    │   ├── types/             # 类型定义
    │   └── main.ts            # 入口文件
    └── package.json           # npm依赖
```

## 快速开始

### 环境要求

- Python 3.8+
- Node.js 16+
- npm 或 yarn

### 后端启动

1. 安装Python依赖：
```bash
cd backend
pip install -r requirements.txt
```

2. 配置环境变量：
```bash
# 复制示例配置文件
cp ../.env.example ../.env

# 编辑 .env 文件，填入必要的API密钥
```

3. 启动后端服务：
```bash
python run.py
```

### 前端启动

1. 安装前端依赖：
```bash
cd frontend
npm install
```

2. 启动开发服务器：
```bash
npm run dev
```

## 配置说明

### 环境变量配置

主要配置项包括：

```bash
# LLM配置（必需）
LLM_API_KEY=your-api-key-here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_ID=gpt-4

# 超时配置（秒）
LLM_TIMEOUT=120

# 高德地图API（可选，用于地点搜索）
AMAP_API_KEY=your-amap-api-key

# Unsplash图片API（可选，用于图片展示）
UNSPLASH_ACCESS_KEY=your-unsplash-key
```

### 超时处理机制

系统实现了智能的超时处理机制：

1. **渐进式超时策略**：
   - 第1次尝试：60秒（快速响应）
   - 第2次尝试：120秒（标准处理）  
   - 第3次尝试：180秒（深度分析）

2. **LLM调用优化**：
   - 默认超时时间：120秒
   - `invoke`方法超时：240秒（双倍时间）
   - 支持环境变量动态配置

3. **错误恢复机制**：
   - 自动重试机制
   - 备用计划生成
   - 详细的错误日志

## API接口

### 旅行规划接口

```
POST /api/trip/plan
```

请求参数：
```json
{
  "city": "北京",
  "start_date": "2024-01-01",
  "end_date": "2024-01-03",
  "travel_days": 3,
  "transportation": "地铁/公交",
  "accommodation": "经济型酒店",
  "preferences": ["历史文化", "美食"],
  "free_text_input": "希望参观故宫和长城"
}
```

## 技术架构

- **后端**：FastAPI + Python 3.11
- **前端**：Vue 3 + TypeScript + Ant Design Vue
- **LLM**：支持多种大语言模型（OpenAI、DeepSeek、千问等）
- **地图服务**：高德地图API
- **图片服务**：Unsplash API

## 故障排除

### 常见问题

1. **LLM调用超时**
   - 检查网络连接
   - 增加`LLM_TIMEOUT`配置值
   - 简化请求内容

2. **API密钥无效**
   - 确认API密钥正确性
   - 检查账户余额和权限
   - 验证base_url配置

3. **服务启动失败**
   - 检查端口占用情况
   - 确认依赖包安装完整
   - 查看详细错误日志

### 日志查看

后端日志会在控制台实时输出，包含：
- 请求处理过程
- LLM调用状态
- 错误和异常信息
- 超时重试记录

## 开发指南

### 代码规范

- 遵循PEP 8 Python编码规范
- 使用类型注解提高代码可读性
- 保持函数单一职责原则

### 测试

```bash
# 后端测试
cd backend
python -m pytest

# 前端测试
cd frontend
npm run test
```

## 贡献指南

欢迎提交Issue和Pull Request！

## 许可证

MIT License
