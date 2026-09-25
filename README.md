# 化工园区事故导排网络 · 检修前泄压校核系统

安全工程师在检修事故导排总管前，录入：

- **一个泄压源**（source）、**一个安全焚烧端**（sink）、若干**汇合节点**（junction）；
- 若干带**方向、最大流量（容量上限）、检修标记**的管段；
- 事故时**必须持续排出的流量**。

提交审计后，服务端对：

1. **正常网络**；
2. **每个被标记为可检修的管段临时移除后的残余网络**；

分别**独立**建立有向图并用 **Dinic 最大流 / 最小割**算法计算最大可导排量。
所有情形的最大流均不低于必须持续排出流量时才返回 `passed` 放行；
否则返回 `failed`，按**管段录入顺序**给出首条失效管段，以及可复核的
**源侧割集节点、焚烧端侧节点、割集管段与割集容量**。

> 每条管段都被视作有向容量上限参与真实最大流计算，**不以局部路径数量代替流量结论**。
> 方向、容量、节点引用无效时直接拒绝审计（HTTP 422），不进行任何流量计算。

## 快速开始（Docker）

```bash
cp .env.example .env          # 可在其中修改宿主机端口 HOST_PORT
docker compose up -d --build  # 默认 http://localhost:8080
```

健康检查：`GET /healthz` → `{"status":"ok"}`（Dockerfile 与 compose 均配置了 healthcheck）。

### 一次性 verify 服务

`verify` 是一次性服务，**自行退出并以退出码报告**以下三项结果：

1. 构建检查（`compileall` 字节码编译）；
2. 代码测试（pytest，24 个用例）；
3. 针对真实运行中 `web` 服务的导排 API 冒烟（健康检查、通过/失败/拒绝/草稿过期全链路）。

```bash
docker compose build
docker compose run --rm verify
echo "verify 退出码：$?"   # 0 = 构建、测试、冒烟全部通过
```

`verify` 通过 `depends_on: condition: service_healthy` 等待 `web` 健康后才开始冒烟。

### 可配置宿主机端口

编辑 `.env`：

```env
HOST_PORT=18080
```

容器内端口固定为 8080，仅宿主机映射端口变化。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET`  | `/healthz` | 健康检查 |
| `GET`  | `/api/draft` | 读取当前草稿及最近一次审计结论（含 `stale` 过期标记） |
| `PUT`  | `/api/draft` | 保存/修改草稿（不产生新结论） |
| `POST` | `/api/audit` | 提交审计，返回正常网络与逐条失效情形的最大流 |
| `GET`  | `/` | 录入页面 |

### 请求示例

```json
{
  "required_flow": 6,
  "nodes": [
    {"id": "SRC", "kind": "source", "label": "泄压源"},
    {"id": "J1",  "kind": "junction"},
    {"id": "J2",  "kind": "junction"},
    {"id": "INC", "kind": "sink", "label": "安全焚烧端"}
  ],
  "pipes": [
    {"id": "P1", "source": "SRC", "target": "J1",  "capacity": 8, "maintainable": true},
    {"id": "P2", "source": "SRC", "target": "J2",  "capacity": 6, "maintainable": true},
    {"id": "P3", "source": "J1",  "target": "INC", "capacity": 6, "maintainable": true},
    {"id": "P4", "source": "J2",  "target": "INC", "capacity": 6, "maintainable": true},
    {"id": "P5", "source": "J1",  "target": "J2",  "capacity": 6, "maintainable": false}
  ]
}
```

### 结论字段（每个情形 scenario）

- `max_flow`：该情形下从泄压源到焚烧端的**最大可导排量**；
- `satisfies` / `shortfall`：是否满足必须流量、缺口；
- `source_cut` / `sink_side`：残余网络上最小割的**源侧割集**与**焚烧端侧节点**；
- `cut_edges` / `cut_capacity`：跨越割 S→T 的管段及**该割集容量**（等于最大流，可手工复核）。

失败时顶层 `failure` 为评估顺序（正常网络在前，其后严格按管段录入顺序）下
**首个不达标的情形**。

### 草稿与旧结论

审计结论带草稿内容指纹（SHA-256 截断）。用户继续修改草稿后：

- `GET /api/draft` 中旧结论的 `stale=true`；
- 页面对旧结论显示“历史结论（已过期）”横幅并置灰标签，**旧结论不会作为新草稿的结果展示**；
- 重新提交审计后生成与当前草稿绑定的新结论。

## 本地开发（无 Docker）

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pytest
uvicorn app.main:app --host 0.0.0.0 --port 8080
BASE_URL=http://127.0.0.1:8080 python scripts/smoke.py
```

## 校验规则（拒绝审计的情形）

- 必须流量或管段最大流量缺失、非正整数、布尔、小数；
- 管段起点/终点缺失、指向不存在的节点（无效节点引用）、起点终点相同（方向无效）；
- 节点或管段编号重复；节点类型不是 source/sink/junction；
- 泄压源或安全焚烧端不恰好各一个；
- 没有管段，或没有任何可检修管段。

## 目录结构

```
app/
  maxflow.py     # Dinic 最大流/最小割引擎
  validation.py  # 草稿结构化校验
  audit.py       # 审计编排（逐情形独立求解、指纹）
  storage.py     # 草稿与结论存储（过期判定）
  main.py        # FastAPI 入口
  tests/         # 引擎/编排/API 测试
frontend/        # 录入页面（原生 HTML/JS，无构建链）
scripts/
  verify.sh      # verify 一次性服务入口（编译→测试→冒烟）
  smoke.py       # 真实业务 API 冒烟
Dockerfile
docker-compose.yml
.env.example
```
