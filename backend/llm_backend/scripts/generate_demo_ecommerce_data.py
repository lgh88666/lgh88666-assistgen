"""Generate demo ecommerce catalog data for AssistGen.

The data is synthetic but shaped like a real smart-home ecommerce catalog:
rich product facts for RAG and explicit product-to-product relations for
knowledge-graph-style recommendation fallback.

Run from backend/llm_backend:
    python scripts/generate_demo_ecommerce_data.py
"""

from __future__ import annotations

import csv
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "app" / "data"
PRODUCTS_CSV = DATA_DIR / "products.csv"
RELATIONS_CSV = DATA_DIR / "product_relations.csv"

RANDOM = random.Random(20260625)


CATEGORY_SPECS = {
    "智能门锁": {
        "brands": ["小米", "华为智选", "鹿客", "德施曼", "凯迪仕", "Aqara"],
        "names": ["指纹门锁", "人脸识别门锁", "电子猫眼门锁", "入户安全门锁", "掌静脉门锁", "租房智能门锁"],
        "price": (599, 2999),
        "features": ["指纹解锁", "临时密码", "门未关提醒", "防撬报警", "远程开门记录", "低电量提醒"],
        "use_cases": ["家庭安防", "老人看护", "出租屋", "新房装修"],
        "targets": ["家庭用户", "独居青年", "有老人家庭", "租房人群"],
    },
    "智能摄像头": {
        "brands": ["小米", "华为智选", "萤石", "360", "TP-LINK", "乐橙"],
        "names": ["云台摄像机", "2K 看家摄像头", "户外防水摄像头", "门口猫眼摄像头", "宝宝看护摄像头", "双摄追踪摄像机"],
        "price": (129, 799),
        "features": ["移动追踪", "双向语音", "夜视增强", "异常声音提醒", "云台巡航", "本地存储"],
        "use_cases": ["家庭安防", "老人看护", "宠物看护", "门口监控"],
        "targets": ["养宠家庭", "有老人家庭", "上班族", "新手爸妈"],
    },
    "智能传感器": {
        "brands": ["Aqara", "米家", "绿米", "海康威视", "涂鸦", "欧瑞博"],
        "names": ["人体传感器", "门窗传感器", "水浸传感器", "烟雾报警器", "燃气报警器", "温湿度传感器"],
        "price": (49, 299),
        "features": ["低功耗", "联动提醒", "异常告警", "免布线安装", "场景自动化", "App 推送"],
        "use_cases": ["家庭安防", "老人看护", "厨房安全", "全屋智能"],
        "targets": ["有老人家庭", "新房装修", "厨房用户", "智能家居入门用户"],
    },
    "智能灯具": {
        "brands": ["Yeelight", "米家", "欧普", "雷士", "飞利浦", "Aqara"],
        "names": ["智能吸顶灯", "护眼台灯", "氛围灯带", "床头阅读灯", "智能筒灯", "客厅主灯"],
        "price": (79, 1299),
        "features": ["无极调光", "色温调节", "语音控制", "定时开关", "场景联动", "护眼模式"],
        "use_cases": ["全屋智能", "卧室助眠", "儿童学习", "客厅氛围"],
        "targets": ["学生家庭", "新房装修", "租房人群", "睡眠敏感人群"],
    },
    "智能插座": {
        "brands": ["公牛", "米家", "Aqara", "华为智选", "涂鸦", "欧瑞博"],
        "names": ["WiFi 智能插座", "计量插座", "空调伴侣", "智能排插", "大功率插座", "迷你智能插座"],
        "price": (39, 299),
        "features": ["远程断电", "用电统计", "定时控制", "过载保护", "语音控制", "节能提醒"],
        "use_cases": ["节能用电", "全屋智能", "租房改造", "家电控制"],
        "targets": ["租房人群", "节能用户", "智能家居入门用户", "家电多的家庭"],
    },
    "智能开关": {
        "brands": ["Aqara", "米家", "欧瑞博", "公牛", "涂鸦", "Yeelight"],
        "names": ["单火智能开关", "零火智能开关", "场景面板", "无线开关", "调光开关", "多键智能开关"],
        "price": (69, 499),
        "features": ["无需换灯", "多路控制", "场景联动", "无线遥控", "语音控制", "状态记忆"],
        "use_cases": ["全屋智能", "新房装修", "卧室控制", "老人夜起"],
        "targets": ["新房装修", "智能改造用户", "有老人家庭", "复式户型"],
    },
    "智能音箱": {
        "brands": ["小米", "华为", "天猫精灵", "百度", "Apple", "小度"],
        "names": ["智能音箱", "屏幕音箱", "儿童学习音箱", "高音质音箱", "中控音箱", "迷你音箱"],
        "price": (89, 1999),
        "features": ["语音助手", "家居中控", "音乐播放", "儿童内容", "视频通话", "红外控制"],
        "use_cases": ["全屋智能", "老人看护", "儿童学习", "客厅娱乐"],
        "targets": ["有老人家庭", "亲子家庭", "音乐用户", "智能家居入门用户"],
    },
    "智能窗帘": {
        "brands": ["Aqara", "米家", "欧瑞博", "杜亚", "绿米", "Yeelight"],
        "names": ["窗帘电机", "梦幻帘电机", "卷帘电机", "轨道套装", "遮光窗帘套装", "免布线窗帘伴侣"],
        "price": (299, 1999),
        "features": ["定时开合", "光照联动", "静音电机", "语音控制", "远程控制", "手拉启动"],
        "use_cases": ["全屋智能", "卧室助眠", "客厅氛围", "老人便利"],
        "targets": ["新房装修", "睡眠敏感人群", "有老人家庭", "大户型家庭"],
    },
    "智能清洁": {
        "brands": ["科沃斯", "石头", "追觅", "米家", "云鲸", "添可"],
        "names": ["扫地机器人", "洗地机", "擦窗机器人", "自清洁扫拖机器人", "基站扫拖机器人", "宠物家庭清洁机器人"],
        "price": (899, 5999),
        "features": ["自动集尘", "自动洗拖布", "避障识别", "地图规划", "毛发防缠绕", "大吸力"],
        "use_cases": ["清洁护理", "宠物家庭", "大户型", "懒人家务"],
        "targets": ["养宠家庭", "上班族", "大户型家庭", "老人家庭"],
    },
    "空气净化器": {
        "brands": ["小米", "352", "飞利浦", "布鲁雅尔", "华为智选", "美的"],
        "names": ["空气净化器", "除甲醛净化器", "母婴净化器", "卧室净化器", "大空间净化器", "宠物除味净化器"],
        "price": (599, 4999),
        "features": ["PM2.5 监测", "除甲醛", "低噪运行", "滤芯提醒", "宠物除味", "睡眠模式"],
        "use_cases": ["空气健康", "母婴家庭", "新房装修", "宠物家庭"],
        "targets": ["母婴家庭", "过敏人群", "新房装修", "养宠家庭"],
    },
    "智能加湿器": {
        "brands": ["米家", "飞利浦", "美的", "小熊", "352", "华为智选"],
        "names": ["无雾加湿器", "恒湿加湿器", "母婴加湿器", "卧室加湿器", "大容量加湿器", "桌面加湿器"],
        "price": (99, 1599),
        "features": ["恒湿控制", "低噪运行", "缺水保护", "银离子抑菌", "大水箱", "睡眠模式"],
        "use_cases": ["空气健康", "卧室助眠", "母婴家庭", "冬季干燥"],
        "targets": ["母婴家庭", "鼻炎人群", "睡眠敏感人群", "北方家庭"],
    },
    "智能空调": {
        "brands": ["美的", "格力", "海尔", "华为智选", "小米", "TCL"],
        "names": ["新风空调", "一级能效空调", "卧室空调", "客厅立式空调", "儿童房空调", "智能挂机空调"],
        "price": (1899, 8999),
        "features": ["一级能效", "新风换气", "睡眠曲线", "App 控制", "自清洁", "温湿联动"],
        "use_cases": ["空气健康", "全屋智能", "卧室助眠", "节能用电"],
        "targets": ["新房装修", "睡眠敏感人群", "母婴家庭", "节能用户"],
    },
    "智能厨房": {
        "brands": ["美的", "苏泊尔", "九阳", "米家", "老板", "方太"],
        "names": ["智能电饭煲", "破壁机", "空气炸锅", "洗碗机", "蒸烤一体机", "智能烟灶套装"],
        "price": (199, 6999),
        "features": ["预约烹饪", "菜谱联动", "自动清洗", "少油烹饪", "火候控制", "远程提醒"],
        "use_cases": ["智能厨房", "健康饮食", "懒人做饭", "新房装修"],
        "targets": ["上班族", "亲子家庭", "新房装修", "厨房小白"],
    },
    "智能冰箱": {
        "brands": ["海尔", "美的", "容声", "TCL", "米家", "卡萨帝"],
        "names": ["多门智能冰箱", "母婴冰箱", "嵌入式冰箱", "对开门冰箱", "保鲜冰箱", "超薄冰箱"],
        "price": (1999, 13999),
        "features": ["食材管理", "分区保鲜", "净味除菌", "变频节能", "App 提醒", "大容量"],
        "use_cases": ["智能厨房", "母婴家庭", "新房装修", "健康饮食"],
        "targets": ["亲子家庭", "大户型家庭", "新房装修", "囤货家庭"],
    },
    "智能洗衣机": {
        "brands": ["小天鹅", "海尔", "美的", "米家", "西门子", "TCL"],
        "names": ["洗烘一体机", "分区洗衣机", "滚筒洗衣机", "母婴洗衣机", "内衣洗衣机", "热泵洗烘套装"],
        "price": (999, 9999),
        "features": ["除菌洗", "智能投放", "烘干护理", "筒自洁", "羊毛洗", "App 预约"],
        "use_cases": ["衣物护理", "母婴家庭", "阳台改造", "懒人家务"],
        "targets": ["母婴家庭", "上班族", "小户型家庭", "衣物护理人群"],
    },
    "智能晾衣架": {
        "brands": ["好太太", "邦先生", "米家", "Aqara", "欧瑞博", "盼盼"],
        "names": ["电动晾衣架", "烘干晾衣架", "阳台晾衣机", "杀菌晾衣架", "薄款晾衣架", "母婴晾衣架"],
        "price": (699, 3999),
        "features": ["电动升降", "照明", "热风烘干", "紫外杀菌", "遇阻即停", "语音控制"],
        "use_cases": ["阳台改造", "衣物护理", "母婴家庭", "全屋智能"],
        "targets": ["母婴家庭", "阳台用户", "新房装修", "老人家庭"],
    },
    "智能网关": {
        "brands": ["Aqara", "米家", "华为智选", "欧瑞博", "涂鸦", "领普"],
        "names": ["多模网关", "蓝牙网关", "Zigbee 网关", "Matter 网关", "全屋中控网关", "红外网关"],
        "price": (129, 999),
        "features": ["多协议接入", "本地自动化", "断网可用", "语音联动", "场景中枢", "Matter 兼容"],
        "use_cases": ["全屋智能", "家庭安防", "节能用电", "新房装修"],
        "targets": ["智能家居进阶用户", "新房装修", "多设备家庭", "技术爱好者"],
    },
}

COMPATIBILITY = ["米家", "华为鸿蒙智联", "Aqara Home", "Apple HomeKit", "天猫精灵", "小度", "Matter", "涂鸦智能"]

RELATION_RULES = {
    "智能门锁": [("智能摄像头", "COMPLEMENTS", "家庭安防"), ("智能传感器", "COMPLEMENTS", "家庭安防"), ("智能网关", "REQUIRES_HUB", "全屋智能")],
    "智能摄像头": [("智能门锁", "COMPLEMENTS", "家庭安防"), ("智能传感器", "COMPLEMENTS", "老人看护")],
    "智能传感器": [("智能灯具", "AUTOMATES", "老人看护"), ("智能网关", "REQUIRES_HUB", "全屋智能"), ("智能插座", "AUTOMATES", "节能用电")],
    "智能音箱": [("智能灯具", "CONTROLS", "全屋智能"), ("智能窗帘", "CONTROLS", "全屋智能"), ("智能插座", "CONTROLS", "节能用电")],
    "智能灯具": [("智能开关", "COMPLEMENTS", "全屋智能"), ("智能音箱", "VOICE_CONTROL", "全屋智能")],
    "智能清洁": [("空气净化器", "COMPLEMENTS", "空气健康"), ("智能加湿器", "COMPLEMENTS", "空气健康")],
    "空气净化器": [("智能加湿器", "COMPLEMENTS", "空气健康"), ("智能空调", "COMPLEMENTS", "空气健康")],
    "智能空调": [("智能插座", "ENERGY_PAIR", "节能用电"), ("空气净化器", "COMPLEMENTS", "空气健康")],
    "智能厨房": [("智能插座", "SAFETY_PAIR", "智能厨房"), ("智能冰箱", "SCENE_MATCH", "智能厨房")],
    "智能冰箱": [("智能厨房", "SCENE_MATCH", "健康饮食")],
    "智能洗衣机": [("智能晾衣架", "COMPLEMENTS", "衣物护理")],
    "智能晾衣架": [("智能洗衣机", "COMPLEMENTS", "衣物护理")],
}


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    products = generate_products()
    relations = generate_relations(products)
    write_products(products)
    write_relations(relations)
    print(f"Generated {len(products)} products -> {PRODUCTS_CSV}")
    print(f"Generated {len(relations)} product relations -> {RELATIONS_CSV}")


def generate_products() -> list[dict[str, object]]:
    products: list[dict[str, object]] = []
    product_id = 1
    for category, spec in CATEGORY_SPECS.items():
        for brand in spec["brands"]:
            for base_name in RANDOM.sample(spec["names"], k=3):
                price_min, price_max = spec["price"]
                price = round_to_price(RANDOM.randint(price_min, price_max))
                rating = round(RANDOM.uniform(4.2, 4.9), 1)
                review_count = RANDOM.randint(80, 4800)
                sales_volume = RANDOM.randint(120, 36000)
                stock = RANDOM.randint(8, 260)
                features = RANDOM.sample(spec["features"], k=4)
                use_cases = RANDOM.sample(spec["use_cases"], k=min(3, len(spec["use_cases"])))
                targets = RANDOM.sample(spec["targets"], k=min(2, len(spec["targets"])))
                compat = RANDOM.sample(COMPATIBILITY, k=RANDOM.randint(2, 4))
                tier = tier_from_price(price, price_min, price_max)
                product_name = f"{brand}{base_name} {tier}"
                tags = sorted(set(features + use_cases + targets + [category, tier]))
                business_weight = round(min(0.45 + rating / 10 + min(sales_volume / 60000, 0.28), 0.98), 3)
                products.append(
                    {
                        "ProductID": product_id,
                        "ProductName": product_name,
                        "CategoryName": category,
                        "SupplierName": supplier_name(brand),
                        "QuantityPerUnit": quantity_for(category),
                        "UnitPrice": price,
                        "UnitsInStock": stock,
                        "Brand": brand,
                        "Description": build_description(product_name, category, use_cases, targets),
                        "Features": "；".join(features),
                        "UseCases": "；".join(use_cases),
                        "TargetUsers": "；".join(targets),
                        "Tags": "；".join(tags),
                        "Rating": rating,
                        "ReviewCount": review_count,
                        "SalesVolume": sales_volume,
                        "BusinessWeight": business_weight,
                        "InstallDifficulty": install_difficulty(category),
                        "AfterSalesPolicy": after_sales_policy(category),
                        "Compatibility": "；".join(compat),
                    }
                )
                product_id += 1
    return products


def generate_relations(products: list[dict[str, object]]) -> list[dict[str, object]]:
    by_category: dict[str, list[dict[str, object]]] = {}
    for product in products:
        by_category.setdefault(str(product["CategoryName"]), []).append(product)

    relations: list[dict[str, object]] = []
    seen: set[tuple[int, int, str]] = set()
    for source_category, targets in RELATION_RULES.items():
        for source in by_category.get(source_category, []):
            source_id = int(source["ProductID"])
            for target_category, relation, scenario in targets:
                candidates = by_category.get(target_category, [])
                if not candidates:
                    continue
                for target in best_targets(candidates, limit=2):
                    target_id = int(target["ProductID"])
                    key = (source_id, target_id, relation)
                    if source_id == target_id or key in seen:
                        continue
                    seen.add(key)
                    weight = round(RANDOM.uniform(0.68, 0.94), 3)
                    relations.append(
                        {
                            "SourceProductID": source_id,
                            "TargetProductID": target_id,
                            "Relation": relation,
                            "Weight": weight,
                            "Scenario": scenario,
                            "Reason": relation_reason(source, target, relation, scenario),
                            "ReasonTags": _relation_tags(relation, scenario),
                            "BusinessWeight": round(RANDOM.uniform(0.50, 0.90), 2),
                        }
                    )

    # Same-category upgrade edges help recommendation explain budget tradeoffs.
    for category, items in by_category.items():
        ordered = sorted(items, key=lambda item: float(item["UnitPrice"]))
        for low, high in zip(ordered[::3], ordered[2::3]):
            key = (int(low["ProductID"]), int(high["ProductID"]), "UPGRADE")
            if key in seen:
                continue
            seen.add(key)
            relations.append(
                {
                    "SourceProductID": low["ProductID"],
                    "TargetProductID": high["ProductID"],
                    "Relation": "UPGRADE",
                    "Weight": round(RANDOM.uniform(0.58, 0.76), 3),
                    "Scenario": "预算升级",
                    "Reason": f"{high['ProductName']} 是 {low['ProductName']} 的更高配置选择，适合预算更高或更看重体验的用户。",
                    "ReasonTags": _relation_tags("UPGRADE", "预算升级"),
                    "BusinessWeight": round(RANDOM.uniform(0.40, 0.70), 2),
                }
            )
    return relations


def write_products(products: list[dict[str, object]]) -> None:
    fieldnames = [
        "ProductID",
        "ProductName",
        "CategoryName",
        "SupplierName",
        "QuantityPerUnit",
        "UnitPrice",
        "UnitsInStock",
        "Brand",
        "Description",
        "Features",
        "UseCases",
        "TargetUsers",
        "Tags",
        "Rating",
        "ReviewCount",
        "SalesVolume",
        "BusinessWeight",
        "InstallDifficulty",
        "AfterSalesPolicy",
        "Compatibility",
    ]
    with PRODUCTS_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(products)


def write_relations(relations: list[dict[str, object]]) -> None:
    fieldnames = ["SourceProductID", "TargetProductID", "Relation", "Weight", "Scenario", "Reason", "ReasonTags", "BusinessWeight"]
    with RELATIONS_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(relations)


def best_targets(products: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    return sorted(products, key=lambda item: (float(item["BusinessWeight"]), float(item["Rating"])), reverse=True)[:limit]


def build_description(name: str, category: str, use_cases: list[str], targets: list[str]) -> str:
    return f"{name} 面向{','.join(targets)}，适合{','.join(use_cases)}场景，可作为{category}类目的主推商品。"


def _relation_tags(relation: str, scenario: str) -> str:
    """Return comma-separated reason tags for a relation type + scenario."""
    tag_map: dict[str, list[str]] = {
        "COMPLEMENTS": ["功能互补", "场景搭配"],
        "BOUGHT_WITH": ["常一起购买", "高关联"],
        "REQUIRES_HUB": ["需要网关", "中枢连接"],
        "CONTROLS": ["可控制", "联动操作"],
        "VOICE_CONTROL": ["语音控制", "智能联动"],
        "UPGRADE": ["配置升级", "体验提升"],
    }
    base = tag_map.get(relation, ["搭配推荐"])
    if scenario and scenario != "预算升级":
        base = [scenario] + base
    return ",".join(base[:3])


def relation_reason(source: dict[str, object], target: dict[str, object], relation: str, scenario: str) -> str:
    if relation == "REQUIRES_HUB":
        return f"{target['ProductName']} 可以作为 {source['ProductName']} 的连接中枢，提升{scenario}联动稳定性。"
    if relation in {"CONTROLS", "VOICE_CONTROL"}:
        return f"{source['ProductName']} 可控制 {target['ProductName']}，适合组成{scenario}语音控制方案。"
    if relation == "UPGRADE":
        return f"{target['ProductName']} 是更高配置选择，适合预算升级。"
    return f"{target['ProductName']} 与 {source['ProductName']} 在{scenario}场景中互补，适合作为搭配推荐。"


def round_to_price(value: int) -> int:
    if value < 300:
        return int(round(value / 10) * 10 - 1)
    if value < 1500:
        return int(round(value / 50) * 50 - 1)
    return int(round(value / 100) * 100 - 1)


def tier_from_price(price: int, min_price: int, max_price: int) -> str:
    ratio = (price - min_price) / max(max_price - min_price, 1)
    if ratio < 0.28:
        return "Lite"
    if ratio < 0.62:
        return "Plus"
    if ratio < 0.84:
        return "Pro"
    return "Max"


def quantity_for(category: str) -> str:
    if category in {"智能灯具"}:
        return "1 盏"
    if category in {"智能插座", "智能开关", "智能传感器"}:
        return "1 个"
    if category in {"智能窗帘"}:
        return "1 套"
    return "1 台"


def supplier_name(brand: str) -> str:
    suffixes = ["官方旗舰店", "智能生活专营店", "生态链旗舰店", "授权专卖店"]
    return f"{brand}{RANDOM.choice(suffixes)}"


def install_difficulty(category: str) -> str:
    if category in {"智能门锁", "智能空调", "智能厨房", "智能冰箱", "智能洗衣机", "智能窗帘", "智能晾衣架"}:
        return "需要预约安装"
    if category in {"智能开关"}:
        return "建议电工安装"
    return "免安装或简单安装"


def after_sales_policy(category: str) -> str:
    if category in {"智能门锁", "智能空调", "智能冰箱", "智能洗衣机", "智能厨房"}:
        return "整机一年质保，核心部件三年质保，支持上门安装"
    return "七天无理由，整机一年质保，支持在线客服"


if __name__ == "__main__":
    main()
