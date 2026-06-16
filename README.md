# 长信宫灯烟道流体仿真与室内空气质量分析系统

汉代长信宫灯复原研究全栈应用系统，集Modbus TCP传感器模拟、烟道流体仿真、PM2.5扩散模型、三维可视化于一体。

## 🏮 系统功能

### 1. 烟道流体仿真模型
- **层流计算**：雷诺数(Re) < 2300，采用Sieder-Tate公式
- **过渡流计算**：2300 ≤ Re < 4000，线性插值加权
- **湍流计算**：Re ≥ 4000，采用Dittus-Boelter公式
- **自然对流**：Grashof数、Rayleigh数耦合计算
- **努塞尔数**：强制对流与自然对流三次方合成
- **烟尘沉降**：Stokes定律计算颗粒沉降速度与效率

### 2. 空气质量分析
- **PM2.5扩散模型**：三维对流扩散方程有限差分数值求解
- **浓度梯度**：三个方向梯度场计算
- **净化效果评估**：基于烟道沉降效率与扩散系数
- **AQI分级**：国标6级空气质量评价
- **健康风险评估**：对应AQI级别的健康建议

### 3. 告警系统（MQTT推送）
- 烟道堵塞告警（烟气流速异常低）
- PM2.5超标告警（75μg/m³警告/150μg/m³严重）
- 烟道温度过高告警
- MQTT主题：`gongdeng/alerts` 和 `gongdeng/sensor`

### 4. 三维可视化（Three.js）
- 长信宫灯精细3D模型（青铜材质、装饰细节）
- 动态火焰与烟雾粒子效果
- 烟道内烟气流线粒子追踪
- 室内PM2.5浓度三维云图

## 📁 项目结构

```
AI_solo_coder_task_A_133/
├── backend/
│   ├── main.py                    # FastAPI入口
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py              # 配置管理
│   │   ├── database.py            # 数据库连接
│   │   ├── models/
│   │   │   └── lamp.py            # SQLAlchemy模型
│   │   ├── schemas/
│   │   │   └── sensor.py          # Pydantic Schema
│   │   ├── services/
│   │   │   ├── flue_simulation.py # 烟道流体仿真核心
│   │   │   ├── air_quality.py     # 空气质量分析
│   │   │   └── alert_service.py   # 告警MQTT服务
│   │   └── routers/
│   │       └── sensor.py          # REST API路由
├── frontend/
│   ├── index.html                 # 主页面
│   └── app.js                     # Three.js可视化逻辑
├── simulator/
│   └── gongdeng_simulator.py      # Modbus TCP传感器模拟器
├── database/
│   └── init.sql                   # TimescaleDB初始化脚本
├── requirements.txt
├── .env.example
└── README.md
```

## 🚀 快速开始

### 1. 环境要求
- Python 3.10+
- PostgreSQL 14+ 与 TimescaleDB 扩展
- MQTT Broker (可选，如Mosquitto)
- Node.js (可选，前端静态服务)

### 2. 数据库初始化

```bash
# 创建数据库并启用TimescaleDB
psql -U postgres -c "CREATE DATABASE changxin_gongdeng;"
psql -U postgres -d changxin_gongdeng -f database/init.sql
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 修改数据库连接等配置
```

### 5. 启动后端服务

```bash
cd backend
python main.py
# 服务将在 http://localhost:8000 启动
# API文档: http://localhost:8000/docs
```

### 6. 启动传感器模拟器（新终端）

```bash
cd simulator
python gongdeng_simulator.py

# 可选参数:
# --lamp-id 1              宫灯ID
# --modbus-host 0.0.0.0    Modbus服务地址
# --modbus-port 502        Modbus端口
# --api-url http://localhost:8000  后端API
# --no-modbus              仅使用HTTP上报
# --no-http                仅使用Modbus TCP
```

### 7. 访问前端

打开浏览器访问 `http://localhost:8000`

## 🔌 API接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/sensor/data` | 上报传感器数据（触发仿真与分析） |
| GET | `/api/sensor/data/latest` | 获取最新综合数据 |
| GET | `/api/sensor/data/history` | 获取传感器历史数据 |
| GET | `/api/simulation/flue/latest` | 获取最新烟道仿真结果 |
| GET | `/api/simulation/air-quality/latest` | 获取最新空气质量分析 |
| GET | `/api/simulation/pm25-grid/latest` | 获取PM2.5三维网格数据 |
| GET | `/api/simulation/particles` | 获取烟气粒子轨迹 |
| GET | `/api/alerts/active` | 获取活跃告警 |
| GET | `/api/alerts/history` | 获取告警历史 |
| POST | `/api/alerts/{id}/resolve` | 确认告警 |
| GET | `/api/statistics` | 获取统计数据 |
| GET | `/health` | 健康检查 |

## 📊 Modbus TCP寄存器映射

| 地址 | 数据 | 缩放 | 单位 |
|------|------|------|------|
| 0 | 灯油消耗速率 | ×100 | ml/min |
| 1 | 烟道温度 | ×100 | °C |
| 2 | 烟气流速 | ×100 | m/s |
| 3 | 室内PM2.5 | ×100 | μg/m³ |
| 4 | 剩余油量 | ×100 | ml |
| 5 | 环境温度 | ×100 | °C |
| 6 | 环境湿度 | ×100 | % |
| 7 | 宫灯ID | ×1 | - |
| 8-9 | 时间戳 | 低16位/高16位 | s |

## 🧪 核心公式

### 烟道流体仿真
```
雷诺数:     Re = ρ·v·d/μ
普朗特数:   Pr = μ·cp/k
格拉晓夫数: Gr = g·β·ΔT·L³/ν²
努塞尔数:   Nu = (Nu_natural³ + Nu_forced³)^(1/3)
压降:       ΔP = f·(L/d)·(ρ·v²/2)
出口温度:   T_out = T_amb + (T_in - T_amb)·exp(-h·P·L/(ṁ·cp))
沉降效率:   η = 0.4·冷却比 + 0.6·停留时间比
```

### PM2.5扩散模型
```
扩散方程: ∂C/∂t = D·(∂²C/∂x² + ∂²C/∂y² + ∂²C/∂z²)
扩散系数: D = D₀·(T/T₀)^1.75·(P₀/P)
```

## 📝 许可证

本项目用于工艺史学术研究用途。
