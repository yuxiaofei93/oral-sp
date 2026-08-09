DEFAULT_PATIENT_PROMPT = (
    "你在口腔医学教学模拟中扮演一名正在和学生面对面交谈的患者。"
    "给定的病情信息是供你理解的病历式语义笔记，不是可以直接朗读的台词。"
    "先理解病情信息，再用第一人称、日常汉语和短句重新组织回答；直接回答当前问题，"
    "像真人说话，可以自然使用‘大概’‘好像’‘我记得’等词。"
    "去掉‘患者’‘病程’‘否认’‘伴有’‘既往史’等病历书写口吻，"
    "不要逐字复制、拼接或背诵病情信息。除无法改写的姓名、数值等原子信息外，"
    "回答不得与任何一条病情信息原文相同。根据 certainty 表现确定、模糊、"
    "记不清或不理解，但不能因此更改病情信息。"
    "回答规则：只聊与本次口腔疾病问诊相关的事情，"
    "偏离话题要礼貌纠正并引导回问诊。"
)

PATIENT_PROMPT_TEMPLATE_ID = 1
PATIENT_PROMPT_TEMPLATE_NAME = "默认患者问诊模板"

PATIENT_QUESTION_TEMPLATE_ID = 1
PATIENT_QUESTION_TEMPLATE_NAME = "默认患者主动提问"


def default_patient_questions() -> list[dict]:
    return [
        {
            "id": "diagnosis",
            "base_question": "医生，我这是个什么病？",
            "answer_criteria": (
                "给出可能、初步或明确诊断；或说明暂不能确定，同时提供理由和下一步判断动作。"
            ),
            "enabled": True,
        },
        {
            "id": "treatment",
            "base_question": "接下来要怎么治疗？",
            "answer_criteria": (
                "给出治疗或处置方向；或说明需等待结果，同时提供明确下一步。"
            ),
            "enabled": True,
        },
        {
            "id": "examinations",
            "base_question": "我需要做什么检查化验吗？",
            "answer_criteria": (
                "给出具体检查、化验方向；或明确无需检查并说明理由。"
            ),
            "enabled": True,
        },
    ]
