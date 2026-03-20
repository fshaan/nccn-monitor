"""Chinese name mapping for NCCN guidelines — enables fuzzy search in Chinese."""

# Mapping: NCCN English name → Chinese name + common aliases
# This enables users to search in Chinese (e.g., "肺癌") and find the right guideline.
GUIDELINE_ZH: dict[str, dict] = {
    # ── Category 1: Cancer by Type (69) ──
    "Acute Lymphoblastic Leukemia": {"zh": "急性淋巴细胞白血病", "aliases": ["急淋", "ALL"]},
    "Acute Myeloid Leukemia": {"zh": "急性髓系白血病", "aliases": ["急髓", "AML"]},
    "Ampullary Adenocarcinoma": {"zh": "壶腹部腺癌", "aliases": ["壶腹癌"]},
    "Anal Carcinoma": {"zh": "肛管癌", "aliases": ["肛门癌"]},
    "Appendiceal Neoplasms and Cancers": {"zh": "阑尾肿瘤", "aliases": ["阑尾癌"]},
    "Basal Cell Skin Cancer": {"zh": "基底细胞皮肤癌", "aliases": ["基底细胞癌", "BCC"]},
    "B-Cell Lymphomas": {"zh": "B细胞淋巴瘤", "aliases": ["B淋巴瘤"]},
    "Biliary Tract Cancers": {"zh": "胆道肿瘤", "aliases": ["胆管癌", "胆囊癌"]},
    "Bladder Cancer": {"zh": "膀胱癌", "aliases": []},
    "Bone Cancer": {"zh": "骨癌", "aliases": ["骨肿瘤"]},
    "Breast Cancer": {"zh": "乳腺癌", "aliases": ["乳癌"]},
    "Castleman Disease": {"zh": "Castleman病", "aliases": ["巨淋巴结增生症"]},
    "Central Nervous System Cancers": {"zh": "中枢神经系统肿瘤", "aliases": ["脑肿瘤", "CNS肿瘤"]},
    "Cervical Cancer": {"zh": "宫颈癌", "aliases": []},
    "Chronic Lymphocytic Leukemia/Small Lymphocytic Lymphoma": {"zh": "慢性淋巴细胞白血病", "aliases": ["慢淋", "CLL", "SLL"]},
    "Chronic Myeloid Leukemia": {"zh": "慢性髓系白血病", "aliases": ["慢粒", "CML"]},
    "Colon Cancer": {"zh": "结肠癌", "aliases": ["结直肠癌"]},
    "Cutaneous Lymphomas": {"zh": "皮肤淋巴瘤", "aliases": ["蕈样肉芽肿"]},
    "Dermatofibrosarcoma Protuberans": {"zh": "隆突性皮肤纤维肉瘤", "aliases": ["DFSP"]},
    "Esophageal and Esophagogastric Junction Cancers": {"zh": "食管/食管胃结合部癌", "aliases": ["食管癌", "食道癌", "GEJ"]},
    "Gastric Cancer": {"zh": "胃癌", "aliases": []},
    "Gastrointestinal Stromal Tumors": {"zh": "胃肠间质瘤", "aliases": ["GIST"]},
    "Gestational Trophoblastic Neoplasia": {"zh": "妊娠滋养细胞肿瘤", "aliases": ["GTN"]},
    "Hairy Cell Leukemia": {"zh": "毛细胞白血病", "aliases": ["HCL"]},
    "Head and Neck Cancers": {"zh": "头颈部肿瘤", "aliases": ["头颈癌"]},
    "Hepatobiliary Cancers": {"zh": "肝胆肿瘤", "aliases": []},
    "Hepatocellular Carcinoma": {"zh": "肝细胞癌", "aliases": ["肝癌", "HCC"]},
    "Histiocytic Neoplasms": {"zh": "组织细胞增生症", "aliases": []},
    "Hodgkin Lymphoma": {"zh": "霍奇金淋巴瘤", "aliases": ["HL"]},
    "Kaposi Sarcoma": {"zh": "卡波西肉瘤", "aliases": []},
    "Kidney Cancer": {"zh": "肾癌", "aliases": ["肾细胞癌", "RCC"]},
    "Melanoma: Cutaneous": {"zh": "皮肤黑色素瘤", "aliases": ["黑色素瘤"]},
    "Melanoma: Uveal": {"zh": "葡萄膜黑色素瘤", "aliases": ["眼黑色素瘤"]},
    "Merkel Cell Carcinoma": {"zh": "Merkel细胞癌", "aliases": ["MCC"]},
    "Mesothelioma: Peritoneal": {"zh": "腹膜间皮瘤", "aliases": []},
    "Mesothelioma: Pleural": {"zh": "胸膜间皮瘤", "aliases": ["间皮瘤"]},
    "Multiple Myeloma": {"zh": "多发性骨髓瘤", "aliases": ["骨髓瘤", "MM"]},
    "Myelodysplastic Syndromes": {"zh": "骨髓增生异常综合征", "aliases": ["MDS"]},
    "Myeloid/Lymphoid Neoplasms with Eosinophilia and Tyrosine Kinase Gene Fusions": {"zh": "伴嗜酸性粒细胞增多的髓系/淋系肿瘤", "aliases": ["MLN-Eo"]},
    "Myeloproliferative Neoplasms": {"zh": "骨髓增殖性肿瘤", "aliases": ["MPN"]},
    "Neuroblastoma": {"zh": "神经母细胞瘤", "aliases": []},
    "Neuroendocrine and Adrenal Tumors": {"zh": "神经内分泌和肾上腺肿瘤", "aliases": ["NET", "神经内分泌瘤"]},
    "Non-Small Cell Lung Cancer": {"zh": "非小细胞肺癌", "aliases": ["肺癌", "NSCLC"]},
    "Occult Primary": {"zh": "原发灶不明肿瘤", "aliases": ["CUP"]},
    "Ovarian Cancer/Fallopian Tube Cancer/Primary Peritoneal Cancer": {"zh": "卵巢癌", "aliases": ["卵巢/输卵管/原发性腹膜癌"]},
    "Pancreatic Adenocarcinoma": {"zh": "胰腺癌", "aliases": ["胰腺腺癌"]},
    "Pediatric Acute Lymphoblastic Leukemia": {"zh": "儿童急性淋巴细胞白血病", "aliases": ["儿童急淋"]},
    "Pediatric Aggressive Mature B-Cell Lymphomas": {"zh": "儿童侵袭性成熟B细胞淋巴瘤", "aliases": []},
    "Pediatric Central Nervous System Cancers": {"zh": "儿童中枢神经系统肿瘤", "aliases": ["儿童脑瘤"]},
    "Pediatric Hodgkin Lymphoma": {"zh": "儿童霍奇金淋巴瘤", "aliases": []},
    "Pediatric Soft Tissue Sarcoma": {"zh": "儿童软组织肉瘤", "aliases": []},
    "Penile Cancer": {"zh": "阴茎癌", "aliases": []},
    "Prostate Cancer": {"zh": "前列腺癌", "aliases": []},
    "Rectal Cancer": {"zh": "直肠癌", "aliases": []},
    "Small Bowel Adenocarcinoma": {"zh": "小肠腺癌", "aliases": ["小肠癌"]},
    "Small Cell Lung Cancer": {"zh": "小细胞肺癌", "aliases": ["SCLC"]},
    "Soft Tissue Sarcoma": {"zh": "软组织肉瘤", "aliases": ["肉瘤"]},
    "Squamous Cell Skin Cancer": {"zh": "鳞状细胞皮肤癌", "aliases": ["鳞癌", "SCC"]},
    "Systemic Light Chain Amyloidosis": {"zh": "系统性轻链淀粉样变性", "aliases": ["AL淀粉样变"]},
    "Systemic Mastocytosis": {"zh": "系统性肥大细胞增多症", "aliases": []},
    "T-Cell Lymphomas": {"zh": "T细胞淋巴瘤", "aliases": ["T淋巴瘤"]},
    "Testicular Cancer": {"zh": "睾丸癌", "aliases": []},
    "Thymomas and Thymic Carcinomas": {"zh": "胸腺瘤和胸腺癌", "aliases": ["胸腺瘤"]},
    "Thyroid Carcinoma": {"zh": "甲状腺癌", "aliases": []},
    "Uterine Neoplasms": {"zh": "子宫肿瘤", "aliases": ["子宫内膜癌"]},
    "Vaginal Cancer": {"zh": "阴道癌", "aliases": []},
    "Vulvar Cancer": {"zh": "外阴癌", "aliases": []},
    "Waldenström Macroglobulinemia/Lymphoplasmacytic Lymphoma": {"zh": "华氏巨球蛋白血症", "aliases": ["WM"]},
    "Wilms Tumor (Nephroblastoma)": {"zh": "肾母细胞瘤", "aliases": ["Wilms瘤"]},
    # ── Category 2: Detection, Prevention & Risk Reduction (7) ──
    "Breast Cancer Risk Reduction": {"zh": "乳腺癌风险降低", "aliases": []},
    "Breast Cancer Screening and Diagnosis": {"zh": "乳腺癌筛查与诊断", "aliases": ["乳腺癌筛查"]},
    "Colorectal Cancer Screening": {"zh": "结直肠癌筛查", "aliases": ["肠癌筛查"]},
    "Genetic/Familial High-Risk Assessment: Breast, Ovarian, Pancreatic, and Prostate": {"zh": "遗传高风险评估：乳腺/卵巢/胰腺/前列腺", "aliases": ["遗传高风险"]},
    "Genetic/Familial High-Risk Assessment: Colorectal, Endometrial, and Gastric": {"zh": "遗传高风险评估：结直肠/子宫内膜/胃", "aliases": []},
    "Lung Cancer Screening": {"zh": "肺癌筛查", "aliases": []},
    "Prostate Cancer Early Detection": {"zh": "前列腺癌早期检测", "aliases": ["前列腺癌早检"]},
    # ── Category 3: Supportive Care (13) ──
    "Adult Cancer Pain": {"zh": "成人癌痛", "aliases": ["癌痛"]},
    "Antiemesis": {"zh": "止吐", "aliases": ["抗呕吐"]},
    "Cancer-Associated Venous Thromboembolic Disease": {"zh": "癌症相关静脉血栓", "aliases": ["癌症血栓", "VTE"]},
    "Cancer-Related Fatigue": {"zh": "癌因性疲劳", "aliases": ["疲劳"]},
    "Distress Management": {"zh": "心理困扰管理", "aliases": ["心理支持"]},
    "Hematopoietic Cell Transplantation": {"zh": "造血干细胞移植", "aliases": ["骨髓移植", "HCT"]},
    "Hematopoietic Growth Factors": {"zh": "造血生长因子", "aliases": ["G-CSF"]},
    "Management of CAR T-Cell and Lymphocyte Engager-Related Toxicities": {"zh": "CAR-T及淋巴细胞衔接器毒性管理", "aliases": ["CAR-T毒性", "CRS"]},
    "Management of Immune Checkpoint Inhibitor-Related Toxicities": {"zh": "免疫检查点抑制剂毒性管理", "aliases": ["免疫治疗毒性", "irAE"]},
    "Palliative Care": {"zh": "姑息治疗", "aliases": ["安宁疗护"]},
    "Prevention and Treatment of Cancer-Related Infections": {"zh": "肿瘤相关感染的预防与治疗", "aliases": ["肿瘤感染"]},
    "Smoking Cessation": {"zh": "戒烟", "aliases": []},
    "Survivorship": {"zh": "肿瘤幸存者管理", "aliases": ["生存者管理"]},
    # ── Category 4: Specific Populations (3) ──
    "Adolescent and Young Adult (AYA) Oncology": {"zh": "青少年及年轻成人肿瘤", "aliases": ["AYA肿瘤"]},
    "Cancer in People with HIV": {"zh": "HIV合并肿瘤", "aliases": ["艾滋病合并肿瘤"]},
    "Older Adult Oncology": {"zh": "老年肿瘤", "aliases": []},
}


def search_guidelines(query: str) -> list[tuple[str, str, float]]:
    """Search guidelines by Chinese name, English name, or alias.

    Returns list of (english_name, chinese_name, relevance_score) sorted by relevance.
    Score: 1.0 = exact match, 0.5+ = substring match.
    """
    query_lower = query.lower().strip()
    results: list[tuple[str, str, float]] = []

    for en_name, info in GUIDELINE_ZH.items():
        zh_name = info["zh"]
        aliases = info.get("aliases", [])
        score = 0.0

        # Exact matches (highest score)
        if query_lower == en_name.lower() or query == zh_name:
            score = 1.0
        elif query_lower in [a.lower() for a in aliases]:
            score = 0.95
        # Substring matches (query is contained in name)
        elif query_lower in en_name.lower():
            score = 0.7
        elif len(query) >= 2 and query in zh_name:
            score = 0.7
        elif any(query_lower in a.lower() for a in aliases):
            score = 0.6

        if score > 0:
            results.append((en_name, zh_name, score))

    results.sort(key=lambda x: -x[2])
    return results


def get_zh_name(en_name: str) -> str:
    """Get Chinese name for an English guideline name."""
    info = GUIDELINE_ZH.get(en_name)
    return info["zh"] if info else en_name
