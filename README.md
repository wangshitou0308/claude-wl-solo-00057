# 维修判定与替换件适配 API

基于 **Python + FastAPI** 实现。HTTP 接收设备型号、硬件修订号、现装部件、
故障代码、测量值与目录版本；先由故障规则判定 **可维修 / 需补充数据 /
禁止维修**，再沿原厂替代链逐候选校验接口、电压、固件下限与必需转接件。

> 核心原则：**任何未知条件都不得默认为兼容**。缺测量值、目录缺字段、
> 版本不可解析等一律产生 `unknown` 证据并拒绝该候选。

## 运行

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload          # http://127.0.0.1:8000/docs
pytest -q                              # 32 个测试
```

## 接口

`POST /api/v1/repair-decisions`

```json
{
  "device_model": "TERM-A7",
  "hardware_revision": "REV-2",
  "installed_part": "SSD-128",
  "fault_code": "F001",
  "catalog_version": "2025.1",
  "measurements": {
    "smart_log": "complete",
    "firmware_version": "2.0.0",
    "temperature_c": 62
  }
}
```

响应固定回显 `catalog_version`（命中的不可变版本），包含顶层 `conclusion`、
规则级证据 `rule_evaluations`、每个候选的 `options`（含 `feasible` 与逐项
`evidence`）及 `evidence_summary`。多个可行方案按
**更换件数量 → 转接步骤 → 部件编号** 稳定排序，被拒候选同样列出拒绝证据。

## 判定流程

1. **版本目录**：版本不存在 → `404 CATALOG_VERSION_NOT_FOUND`（locator 指向
   版本，context 给出可用版本）。
2. **实体解析**：未知型号 / 修订号 / 部件 / 故障代码 → `422` 结构化错误。
3. **故障规则（三值逻辑）**：条件全真才 `fired`；有未知且无明确假 →
   `needs_data`；任一明确假 → `not_applicable`。按优先级聚合：
   - 最高活跃优先级上 fired 规则结论互斥 →
     `409 RULE_CONFLICT`（locator 定位到每条冲突规则）；
   - `repairable` 同层存在缺数据规则 → 降级 `need_data`；
   - `forbidden` 优先级最高时短路，不评估替代链。
4. **替代链遍历**：迭代 DFS + 三色标记，遇灰节点即
   `409 REPLACEMENT_CHAIN_CYCLE`，context 给出完整环路径、locator 逐边定位；
   黑节点为跨边，不重复展开。
5. **候选适配（固定顺序，逐项证据）**：候选存在 → 槽位接口 →
   直换/转接场景一致性 → 转接件存在 → 接口桥接（源/目标）→
   电压（候选与转接件）→ 固件下限（缺测量/不可解析=unknown）→ 额外更换件。
   - 有可行方案 → `repairable`；
   - 有候选仅因 unknown 被拒 → `need_data`；
   - 全部硬不兼容 → `forbidden`。

错误统一信封：

```json
{"error": {"code": "...", "message": "...",
           "locators": [{"kind": "fault_rule|chain_edge|...", "id": "...",
                         "detail": "..."}],
           "context": {}}}
```

## 版本不可变

目录文件 `catalogs/catalog-<version>.json` 在启动时一次性加载为冻结对象
（frozen dataclass + `MappingProxyType`）。注册表只新增版本、从不就地改写；
旧版本请求固定回显旧版本号。新版本（如 `2025.2`）加入新配件/规则后，
钉在 `2025.1` 的同一请求结论保持字节级不变（见
`tests/test_catalog_versions.py`）。

## 分层结构（四层分离）

```
app/
  api/
    schemas.py          # 请求校验（Pydantic，仅形状/类型）
    error_handlers.py   # HTTP 错误映射：DomainError/校验异常 -> 结构化信封
    routes.py / app.py  # 路由与装配（依赖注入注册表与引擎）
  catalog/
    models.py           # 冻结目录模型（部件/链边/设备/规则）
    loader.py           # JSON -> Catalog，结构校验
    registry.py         # 按版本不可变加载与查找
  engine/
    errors.py           # 领域错误 + 规则/链路 Locator
    rules.py            # 故障规则三值求值
    chain.py            # 替代链遍历与环检测
    compatibility.py    # 接口/电压/固件/转接件适配
    decision.py         # 判定引擎编排与结论聚合
    evidence.py         # 证据/候选/判定结果模型
    versioning.py       # 固件版本比较（无法解析=未知）
  main.py               # uvicorn 入口
catalogs/               # 版本化目录快照
tests/                  # 直换/转接/数据不足/矛盾规则/替代环/版本不可变...
```
