"""Small, auditable method and skill discovery for single-task intake.

The default catalog is local and deterministic, so planning remains usable
offline. Hosts may inject a searcher for fresh web/repository research; its
results are recommendations only and still require user confirmation.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Callable, Iterable


MethodSearcher = Callable[[str, list[str]], list[dict[str, Any]]]
SkillSearcher = Callable[[str, list[str]], list[dict[str, Any]]]

PROGRESSIVE_DISCLOSURE_POLICY = {
    "metadata": "startup_or_inventory",
    "instructions": "load_after_match",
    "references_and_scripts": "load_on_demand",
}

METHOD_CATALOG_VERSION = "2026-09-02"
METHOD_SOURCE_REGISTRY = {
    "makecrew": {
        "label": "MakeCrew 内置流程",
        "license": "MIT",
        "url": "https://github.com/GodMaking/makecrew",
    },
    "dbskill": {
        "label": "dbskill 公开机制参考",
        "license": "CC BY-NC 4.0",
        "url": "https://github.com/dontbesilent2025/dbskill",
        "version": "2.18.39",
        "commit": "86e3125bc3a327dbaef4c490c221034a28c9eff6",
        "usage": "只借鉴公开方法结构，不复制源码、提示词原文或知识原文",
    },
}

LOCAL_METHODS: dict[str, list[dict[str, Any]]] = {
    "工程": [{
        "name": "规格先行 + 增量实现",
        "method_id": "engineering-spec-incremental",
        "approach": "先确认接口、页面状态和验收标准，再分小步实现并回归",
        "skill_ids": ["interview-me", "planning-and-task-breakdown", "test-driven-development", "frontend-ui-engineering"],
        "why": "适合已有项目，能减少需求误解和返工",
        "source": "MakeCrew 内置工程流程",
        "when_to_use": ["已有项目", "修复或增量功能", "需要回归测试"],
        "boundaries": ["不替代产品范围确认", "共享文件的并发修改仍需调度"],
        "deliverables": ["实现变更", "测试结果", "变更说明"],
        "acceptance_gates": ["测试或构建通过", "关键流程可复现"],
        "cost": "低到中：按变更范围读取代码",
        "evidence_level": "built_in",
    }, {
        "name": "产品交付门禁",
        "method_id": "product-delivery-gates",
        "approach": "需求简报 -> Demo/原型 -> 技术设计 -> 增量实现 -> 独立验收",
        "skill_ids": ["product-delivery", "planning-and-task-breakdown", "verification-before-completion"],
        "why": "适合新建或大幅重做网站、应用和产品，先确认方案再投入编码",
        "source": "MakeCrew 内置工程流程",
        "when_to_use": ["新建网站", "大幅重做产品", "用户要求先看方案"],
        "boundaries": ["小修复不进入完整产品门禁", "Demo 不是生产交付"],
        "deliverables": ["项目简报", "Demo/原型", "技术设计", "实现与验收报告"],
        "acceptance_gates": ["用户确认范围", "实现与验收标准一致"],
        "cost": "中：确认阶段增加规划轮次，减少后续返工",
        "evidence_level": "built_in",
    }],
    "研究": [{
        "name": "来源驱动研究",
        "method_id": "research-source-first",
        "approach": "优先查官方文档和一手资料，记录日期、链接与证据边界",
        "skill_ids": ["source-driven-development", "verification-before-completion"],
        "why": "适合需要可核验结论的调研任务",
        "source": "MakeCrew 内置研究流程",
        "when_to_use": ["需要最新事实", "比较方案", "结论需要引用"],
        "boundaries": ["搜索结果不是事实本身", "没有来源时标注待核实"],
        "deliverables": ["结论", "来源与日期", "不确定性"],
        "acceptance_gates": ["关键判断可追溯", "来源日期明确"],
        "cost": "低到中：只读取与问题相关的来源",
        "evidence_level": "built_in",
    }, {
        "name": "理论-案例-反例研究",
        "method_id": "research-theory-case-counterexample",
        "approach": "先定义问题机制，再查理论与一手来源，找结构同构的成功、失败与反例，最后写适用条件和失效边界",
        "skill_ids": ["source-driven-development", "verification-before-completion"],
        "why": "适合复杂判断、框架比较和借鉴研究，避免只堆链接或只讲单个成功故事",
        "source": "MakeCrew 方法卡（借鉴 dbskill 公开研究结构，重新实现）",
        "source_url": "https://github.com/dontbesilent2025/dbskill",
        "source_license": "CC BY-NC 4.0",
        "when_to_use": ["复杂决策", "理论依据", "历史案例", "标准答案", "借鉴"],
        "boundaries": ["类比不能单独证明因果", "资料数量不等于结论强度"],
        "deliverables": ["直接答案", "理论/来源表", "案例矩阵", "适用条件与失效边界"],
        "acceptance_gates": ["关键判断有来源或明确标注推断", "覆盖正例与反例或失败案例"],
        "cost": "中：只在问题需要解释机制或用户明确要求研究时展开",
        "evidence_level": "inspired_pattern",
    }, {
        "name": "可迁移对标筛选",
        "method_id": "benchmark-transferability",
        "approach": "按目标、用户、约束、结果机制和可迁移动作筛选对象，再区分可学机制与不可复制表象",
        "skill_ids": ["source-driven-development", "verification-before-completion"],
        "why": "降低只看流量、名气或表面形式造成的错误模仿",
        "source": "MakeCrew 方法卡（借鉴 dbskill 公开对标框架，重新实现）",
        "source_url": "https://github.com/dontbesilent2025/dbskill",
        "source_license": "CC BY-NC 4.0",
        "when_to_use": ["找对标", "竞品研究", "借鉴项目", "选择模仿对象"],
        "boundaries": ["模仿机制不等于复制内容", "主体、平台和资源差异必须单独标注"],
        "deliverables": ["候选对象", "筛选理由", "可迁移机制", "最小验证动作"],
        "acceptance_gates": ["每个候选有可核验依据", "至少区分一个可学点和一个不可迁移点"],
        "cost": "中：先小样本筛选，再深入研究入选对象",
        "evidence_level": "inspired_pattern",
    }],
    "内容": [{
        "name": "受众问题先行",
        "method_id": "content-audience-first",
        "approach": "先明确受众欲望和单一承诺，再产出平台版本并检查事实",
        "skill_ids": ["interview-me", "source-driven-development", "verification-before-completion"],
        "why": "避免同时塞入多个卖点导致表达失焦",
        "source": "MakeCrew 内置内容流程",
        "when_to_use": ["选题", "文案", "视频脚本", "宣传内容"],
        "boundaries": ["不以流量指标替代事实核验", "一条内容只保留一个主要承诺"],
        "deliverables": ["受众问题", "单一承诺", "平台版本", "事实核验项"],
        "acceptance_gates": ["目标受众明确", "事实与引用可核验"],
        "cost": "低到中：先处理当前内容，不扫描全部历史素材",
        "evidence_level": "built_in",
    }, {
        "name": "内容资产单元 + 主题地图",
        "method_id": "content-asset-map",
        "approach": "将原始素材拆为带来源的内容单元，建立主题、受众和证据关系，再输出可重组的选题或稿件",
        "skill_ids": ["source-driven-development", "context-engineering", "verification-before-completion"],
        "why": "大量内容时减少重复阅读和重写，让素材可以追溯、复用和持续生长",
        "source": "MakeCrew 方法卡（借鉴 dbskill 公开内容资产结构，重新实现）",
        "source_url": "https://github.com/dontbesilent2025/dbskill",
        "source_license": "CC BY-NC 4.0",
        "when_to_use": ["素材很多", "整理旧文稿", "建立主题地图", "内容复用"],
        "boundaries": ["少量素材不进入重型工程", "原始文件仍是事实来源，摘要不替代原件"],
        "deliverables": ["素材清单", "内容单元", "主题关系", "可重组草稿"],
        "acceptance_gates": ["抽样内容单元能回到原件", "未处理范围和重复候选可见"],
        "cost": "中到高：先审计规模，再分批处理，不一次读取全部素材",
        "evidence_level": "inspired_pattern",
    }, {
        "name": "发布前双层检查",
        "method_id": "content-two-layer-review",
        "approach": "分别检查平台可能识别的机器信号与内容本身的事实、隐私、权益和表述问题，只改具体位置并保留表达风格",
        "skill_ids": ["verification-before-completion"],
        "why": "把发布前检查变成可执行的局部动作，避免把关键词误判当成结论",
        "source": "MakeCrew 方法卡（借鉴 dbskill 公开发布检查思路，重新实现）",
        "source_url": "https://github.com/dontbesilent2025/dbskill",
        "source_license": "CC BY-NC 4.0",
        "when_to_use": ["发布前检查", "短视频审核", "标题/字幕检查", "内容排雷"],
        "boundaries": ["只根据提供的材料判断", "平台结果仍以实际审核为准"],
        "deliverables": ["具体位置", "可能原因", "最小修改动作", "待确认项"],
        "acceptance_gates": ["机器信号与内容问题分开", "每条建议定位到原文或画面"],
        "cost": "低：按提交的内容检查，不扫描无关资料",
        "evidence_level": "inspired_pattern",
    }],
    "设计": [{
        "name": "信息层级 + 目标尺寸验证",
        "method_id": "design-hierarchy-size-check",
        "approach": "先定信息层级和组件约束，再做目标尺寸预览与可访问性检查",
        "skill_ids": ["frontend-ui-engineering", "verification-before-completion"],
        "why": "适合需要可读、可用和可复用视觉交付的任务",
        "source": "MakeCrew 内置设计流程",
        "when_to_use": ["界面设计", "响应式页面", "视觉交付"],
        "boundaries": ["不代替业务需求确认", "视觉预览不能代替真实设备验证"],
        "deliverables": ["信息层级", "组件约束", "目标尺寸预览", "可访问性检查"],
        "acceptance_gates": ["目标尺寸可读", "关键交互可操作"],
        "cost": "低到中：只验证目标尺寸和关键状态",
        "evidence_level": "built_in",
    }],
    "知识库": [{
        "name": "范围盘点 + 抽样核验",
        "method_id": "knowledge-scope-sample",
        "approach": "先盘点资料范围和索引，再抽样核对引用与待处理清单",
        "skill_ids": ["source-driven-development", "context-engineering", "verification-before-completion"],
        "why": "控制大规模资料整理的遗漏和上下文成本",
        "source": "MakeCrew 内置知识库流程",
        "when_to_use": ["首次建立知识库", "大型资料整理", "索引质量检查"],
        "boundaries": ["先读元数据再读正文", "抽样结果不能冒充全量完成"],
        "deliverables": ["范围报告", "索引计划", "抽样核验结果"],
        "acceptance_gates": ["处理范围明确", "抽样引用可回到原件"],
        "cost": "低到中：先计划后增量同步",
        "evidence_level": "built_in",
    }, {
        "name": "导航-原件-增量审计",
        "method_id": "knowledge-navigation-incremental-audit",
        "approach": "先盘点范围和来源，再建立权威导航，按变更增量同步；查询时只展开命中原件，定期检查冲突与失效路径",
        "skill_ids": ["context-engineering", "source-driven-development", "verification-before-completion"],
        "why": "借鉴文件夹知识库治理经验，同时保持 MakeCrew 的作用域权限和自适应检索",
        "source": "MakeCrew 方法卡（借鉴 dbskill 公开知识库治理结构，重新实现）",
        "source_url": "https://github.com/dontbesilent2025/dbskill",
        "source_license": "CC BY-NC 4.0",
        "when_to_use": ["共享项目记忆", "本地文件夹知识库", "版本冲突", "长期维护"],
        "boundaries": ["导航只负责指路，原件才是事实来源", "不能绕过员工的项目作用域"],
        "deliverables": ["权威导航", "来源关系", "增量同步记录", "冲突/失效报告"],
        "acceptance_gates": ["每条结论可追溯到原件", "权限过滤先于检索", "未变化文件不重复处理"],
        "cost": "中：只同步变化范围，查询时按需展开证据",
        "evidence_level": "inspired_pattern",
    }],
    "技能": [{
        "name": "触发条件驱动开发",
        "method_id": "skill-trigger-contract",
        "approach": "先定义触发/不触发、输入输出和最小回归，再编写 Skill",
        "skill_ids": ["interview-me", "context-engineering", "verification-before-completion"],
        "why": "让 Skill 在正确任务上触发且方便验证",
        "source": "MakeCrew 内置 Skill 流程",
        "when_to_use": ["制作 Skill", "更新 Skill", "排查误触发"],
        "boundaries": ["不把宿主缺失的工具伪装成已接入", "行为验证不能只看文件存在"],
        "deliverables": ["行为契约", "SKILL.md", "正例/近邻反例/缺资源测试"],
        "acceptance_gates": ["元数据通过", "主要触发和近邻反例可验证"],
        "cost": "低到中：先做结构校验，再做最小行为测试",
        "evidence_level": "built_in",
    }],
}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(entry).strip() for entry in value if str(entry).strip()]
    if value is None:
        return []
    value = str(value).strip()
    return [value] if value else []


def _normalize_candidates(
    raw_items: Iterable[Any],
    normalizer: Callable[[Any], dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Keep valid candidates when a host returns one malformed item."""
    valid: list[dict[str, Any]] = []
    invalid_count = 0
    for raw in raw_items:
        try:
            valid.append(normalizer(raw))
        except (AttributeError, TypeError, ValueError):
            invalid_count += 1
    return valid, invalid_count


def _normalize(item: dict[str, Any], *, source: str) -> dict[str, Any]:
    def text_list(value: Any) -> list[str]:
        if isinstance(value, (list, tuple)):
            return [str(entry).strip() for entry in value if str(entry).strip()]
        if value is None:
            return []
        value = str(value).strip()
        return [value] if value else []

    if not isinstance(item, dict):
        raise TypeError("方法候选必须是对象")
    name = str(item.get("name") or item.get("title") or "候选方法").strip()
    item_source = str(item.get("source") or source).strip()
    method_id = str(item.get("method_id") or "").strip()
    if not method_id:
        digest = hashlib.sha1(f"{item_source}\n{name}".encode("utf-8")).hexdigest()[:12]
        method_id = f"external-{digest}" if item_source != "MakeCrew 内置流程" else f"builtin-{digest}"
    return {
        "method_id": method_id,
        "name": name,
        "approach": str(item.get("approach") or item.get("summary") or "待补充").strip(),
        "skill_ids": _string_list(item.get("skill_ids")),
        "why": str(item.get("why") or item.get("reason") or "与当前任务相关").strip(),
        "source": item_source,
        "source_kind": "external" if source == "宿主搜索结果" else "local",
        "when_to_use": text_list(item.get("when_to_use")),
        "boundaries": text_list(item.get("boundaries")),
        "deliverables": text_list(item.get("deliverables")),
        "acceptance_gates": text_list(item.get("acceptance_gates")),
        "cost": str(item.get("cost") or "按当前任务评估").strip(),
        "evidence_level": str(item.get("evidence_level") or "candidate").strip(),
        "source_url": str(item.get("source_url") or "").strip(),
        "source_license": str(item.get("source_license") or "").strip(),
    }


def _query_signals(text: str) -> list[str]:
    """Extract compact phrase signals for deterministic, language-tolerant ranking."""
    normalized = text.lower()
    signals = re.findall(r"[a-z0-9][a-z0-9_-]+|[\u4e00-\u9fff]{2,}", normalized)
    # Chinese requests are often written without spaces. Short n-grams retain
    # useful intent ("主题地图", "发布前") without loading a tokenizer.
    for phrase in re.findall(r"[\u4e00-\u9fff]+", normalized):
        for size in (2, 3, 4):
            signals.extend(phrase[index:index + size] for index in range(len(phrase) - size + 1))
    return list(dict.fromkeys(signal for signal in signals if signal))


def _rank_methods(
    task: str,
    methods: Iterable[dict[str, Any]],
    *,
    prefer_external: bool = False,
) -> list[dict[str, Any]]:
    """Rank cards by explicit task overlap while retaining a useful fallback order."""
    signals = _query_signals(task)
    ranked: list[dict[str, Any]] = []
    for position, method in enumerate(methods):
        searchable = " ".join([
            method.get("name", ""), method.get("approach", ""), method.get("why", ""),
            " ".join(method.get("when_to_use", [])),
            " ".join(method.get("deliverables", [])),
        ]).lower()
        matched = [signal for signal in signals if signal in searchable]
        exact_phrases = [
            phrase for phrase in method.get("when_to_use", []) + [method.get("name", "")]
            if phrase and phrase.lower() in task.lower()
        ]
        matched = list(dict.fromkeys([*exact_phrases, *matched]))
        overlap = len(matched) / max(1, len(signals))
        score = min(1.0, (0.65 if exact_phrases else 0.0) + min(0.35, overlap * 2.5))
        ranked_item = dict(method)
        ranked_item["relevance_score"] = round(score, 4)
        ranked_item["match_reasons"] = (
            [f"任务命中：{phrase}" for phrase in exact_phrases[:3]]
            or ["任务与方法的适用信号有重叠" for _ in [0]] if matched
            else ["同领域备用方法，需结合任务判断"]
        )
        ranked_item["selection_rank"] = position + 1
        ranked.append(ranked_item)
    # A fresh host search is an explicit request for current candidates. Keep
    # those candidates ahead of the local fallback, while still ranking each
    # source by task overlap. Routine local-first planning never sets this flag.
    ranked.sort(key=lambda item: (
        0 if prefer_external and item.get("source_kind") == "external" else 1,
        -item["relevance_score"],
        item["selection_rank"],
        item["method_id"],
    ))
    for rank, item in enumerate(ranked, start=1):
        item["selection_rank"] = rank
    return ranked


def audit_method_catalog() -> dict[str, Any]:
    """Validate built-in cards before they are exposed to a host or publisher."""
    issues: list[dict[str, str]] = []
    ids: set[str] = set()
    card_count = 0
    required = ("method_id", "name", "approach", "when_to_use", "boundaries", "deliverables", "acceptance_gates", "cost", "evidence_level")
    for domain, cards in LOCAL_METHODS.items():
        for raw in cards:
            card_count += 1
            if not str(raw.get("method_id") or "").strip():
                issues.append({"code": "missing_method_id", "domain": domain, "name": str(raw.get("name") or "")})
            card = _normalize(raw, source="MakeCrew 内置流程")
            if card["method_id"] in ids:
                issues.append({"code": "duplicate_method_id", "domain": domain, "method_id": card["method_id"]})
            ids.add(card["method_id"])
            for field in required:
                if not card.get(field):
                    issues.append({"code": "missing_field", "domain": domain, "method_id": card["method_id"], "field": field})
    return {
        "status": "pass" if not issues else "review",
        "catalog_version": METHOD_CATALOG_VERSION,
        "card_count": card_count,
        "source_count": len(METHOD_SOURCE_REGISTRY),
        "issues": issues,
    }


def _normalize_skill(item: dict[str, Any]) -> dict[str, str]:
    if not isinstance(item, dict):
        raise TypeError("Skill 候选必须是对象")
    skill_id = str(item.get("skill_id") or item.get("id") or item.get("name") or "").strip()
    return {
        "skill_id": skill_id,
        "name": str(item.get("name") or skill_id or "候选 Skill").strip(),
        "description": str(item.get("description") or item.get("summary") or item.get("why") or "与当前任务相关").strip(),
        "source": str(item.get("source") or item.get("url") or "宿主搜索结果").strip(),
    }


def discover_methods(
    task: str,
    domains: list[str],
    *,
    searcher: MethodSearcher | None = None,
    search_external: bool | None = None,
) -> dict[str, Any]:
    """Match local methods first, then optionally expand to host search."""
    if domains == ["待澄清"]:
        return {
            "status": "deferred_until_clear",
            "catalog_version": METHOD_CATALOG_VERSION,
            "catalog_sources": {},
            "query": task,
            "methods": [],
            "local_match_count": 0,
            "external_result_count": 0,
            "returned_count": 0,
            "external_searched": False,
            "search_error": "",
        }

    local_methods: list[dict[str, Any]] = []
    for domain in domains:
        local_methods.extend(_normalize(item, source="MakeCrew 内置流程") for item in LOCAL_METHODS.get(domain, []))
    methods: list[dict[str, Any]] = []
    search_error = ""
    should_search_external = searcher is not None and (
        search_external is not False or not local_methods
    )
    external_searched = False
    status = "local_match" if local_methods else "no_local_match"
    external_result_count = 0
    invalid_external_result_count = 0
    if should_search_external:
        external_searched = True
        try:
            raw_external = list(searcher(task, domains) or [])
            external_result_count = len(raw_external)
            normalized, invalid_external_result_count = _normalize_candidates(
                raw_external,
                lambda item: _normalize(item, source="宿主搜索结果"),
            )
            methods.extend(normalized)
            status = "searched"
        except Exception as exc:  # host search is advisory; local planning remains usable
            status = "local_fallback"
            search_error = f"{type(exc).__name__}: {exc}"
    methods.extend(local_methods)
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for method in methods:
        key = (method["name"], method["source"])
        if key not in seen:
            seen.add(key)
            deduped.append(method)
    ranked = _rank_methods(task, deduped, prefer_external=external_searched)
    return {
        "status": status,
        "catalog_version": METHOD_CATALOG_VERSION,
        "catalog_sources": METHOD_SOURCE_REGISTRY.copy(),
        "query": task,
        "methods": ranked[:8],
        "local_match_count": len(local_methods),
        "external_result_count": external_result_count,
        "returned_count": min(8, len(ranked)),
        "invalid_external_result_count": invalid_external_result_count,
        "external_searched": external_searched,
        "search_error": search_error,
    }


def resolve_skills(
    task: str,
    required_skill_ids: list[str],
    installed_skill_ids: list[str],
    *,
    searcher: SkillSearcher | None = None,
    defer: bool = False,
) -> dict[str, Any]:
    """Match installed skills and search only for unresolved capability gaps."""
    required = list(dict.fromkeys(skill_id.strip() for skill_id in required_skill_ids if skill_id.strip()))
    installed = {skill_id.strip() for skill_id in installed_skill_ids if skill_id.strip()}
    if defer:
        return {
            "status": "deferred_until_clear",
            "local_checked": False,
            "required_skill_ids": required,
            "matched_skill_ids": [],
            "missing_skill_ids": required,
            "external_searched": False,
            "candidates": [],
            "search_error": "",
            "requires_user_decision": False,
            "decision_prompt": "",
            "external_result_count": 0,
            "returned_count": 0,
            "invalid_candidate_count": 0,
            "load_policy": PROGRESSIVE_DISCLOSURE_POLICY.copy(),
        }

    matched = [skill_id for skill_id in required if skill_id in installed]
    missing = [skill_id for skill_id in required if skill_id not in installed]
    if not missing:
        return {
            "status": "local_match",
            "local_checked": True,
            "required_skill_ids": required,
            "matched_skill_ids": matched,
            "missing_skill_ids": [],
            "external_searched": False,
            "candidates": [],
            "search_error": "",
            "requires_user_decision": False,
            "decision_prompt": "",
            "external_result_count": 0,
            "returned_count": 0,
            "invalid_candidate_count": 0,
            "load_policy": PROGRESSIVE_DISCLOSURE_POLICY.copy(),
        }

    if searcher is None:
        return {
            "status": "search_adapter_required",
            "local_checked": True,
            "required_skill_ids": required,
            "matched_skill_ids": matched,
            "missing_skill_ids": missing,
            "external_searched": False,
            "candidates": [],
            "search_error": "",
            "requires_user_decision": False,
            "decision_prompt": "请启用宿主 Skill 搜索能力，查找缺失能力的候选实现。",
            "external_result_count": 0,
            "returned_count": 0,
            "invalid_candidate_count": 0,
            "load_policy": PROGRESSIVE_DISCLOSURE_POLICY.copy(),
        }

    external_result_count = 0
    invalid_candidate_count = 0
    try:
        raw_candidates = list(searcher(task, missing) or [])
        external_result_count = len(raw_candidates)
        candidates, invalid_candidate_count = _normalize_candidates(raw_candidates, _normalize_skill)
        candidates = [item for item in candidates if item["skill_id"]]
        deduped: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for candidate in candidates:
            key = (candidate["skill_id"], candidate["source"])
            if key not in seen:
                seen.add(key)
                deduped.append(candidate)
    except Exception as exc:
        return {
            "status": "search_failed",
            "local_checked": True,
            "required_skill_ids": required,
            "matched_skill_ids": matched,
            "missing_skill_ids": missing,
            "external_searched": True,
            "candidates": [],
            "search_error": f"{type(exc).__name__}: {exc}",
            "requires_user_decision": False,
            "decision_prompt": "保留已匹配 Skill，修复搜索适配器后继续查找缺失能力。",
            "external_result_count": external_result_count,
            "returned_count": 0,
            "invalid_candidate_count": invalid_candidate_count,
            "load_policy": PROGRESSIVE_DISCLOSURE_POLICY.copy(),
        }

    if not deduped:
        return {
            "status": "no_candidates",
            "local_checked": True,
            "required_skill_ids": required,
            "matched_skill_ids": matched,
            "missing_skill_ids": missing,
            "external_searched": True,
            "candidates": [],
            "search_error": "",
            "requires_user_decision": False,
            "decision_prompt": "当前没有找到合适候选，可调整搜索来源或由现有能力执行。",
            "external_result_count": external_result_count,
            "returned_count": 0,
            "invalid_candidate_count": invalid_candidate_count,
            "load_policy": PROGRESSIVE_DISCLOSURE_POLICY.copy(),
        }

    return {
        "status": "candidates_found",
        "local_checked": True,
        "required_skill_ids": required,
        "matched_skill_ids": matched,
        "missing_skill_ids": missing,
        "external_searched": True,
        "candidates": deduped[:8],
        "external_result_count": external_result_count,
        "returned_count": min(8, len(deduped)),
        "invalid_candidate_count": invalid_candidate_count,
        "search_error": "",
        "requires_user_decision": True,
        "decision_prompt": "本地缺少部分匹配 Skill。请选择是否安装并使用上述候选，或继续使用现有能力。",
        "load_policy": PROGRESSIVE_DISCLOSURE_POLICY.copy(),
    }
