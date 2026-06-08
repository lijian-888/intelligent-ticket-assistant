"""Mock ticket data used before the real ticket system API is available."""

from app.models import Ticket


MOCK_TICKETS: list[Ticket] = [
    # 完整投诉样例：南大街命中建国路承办单位。
    Ticket(
        title="要求部门协调按消协规定赔偿。",
        content=(
            "服务对象5月25日通过网络平台在某医疗器械用品店（某商业综合体，"
            "订单号DEMO-ORDER-001）消费15.85元购买脚臭粉，宣传可以去除脚臭，"
            "发现商品文号是企业执行标准，暗示有医疗功效，虚假宣传，要求部门协调按消协规定赔偿。"
        ),
        ticket_no="DEMO-TICKET-001",
        ticket_type="民生服务->权益保障",
        contact_phone="demo-phone-001",
        customer_name="未知",
        created_at="2026-05-28 13:49:09",
        due_at="2026-06-10 12:00:32",
        region="北京市朝阳区",
        incident_at="2026-05-28 13:48:00",
        incident_address="北京市北京市朝阳区",
        third_party_ticket_no="DEMO-THIRD-PARTY-001",
        attachments=["订单截图.jpg", "商品宣传页.jpg"],
    ),
    # 完整举报样例：强调违法线索和依法查处，世纪大道街道命中世纪大道承办单位。
    Ticket(
        title="举报某便利店销售过期食品",
        content=(
            "本人在北京市北京市朝阳区世纪大道街道和丰大厦附近某便利店购买酸奶，回家后发现已经超过保质期。"
            "店内货架还有多瓶同批次过期食品，要求市场监管部门依法查处并反馈处理结果。"
        ),
        ticket_no="DEMO-TICKET-002",
        ticket_type="民生服务->食品安全",
        contact_phone="demo-phone-002",
        customer_name="张某",
        created_at="2026-05-29 09:00:12",
        due_at="2026-06-12 18:00:00",
        region="北京市朝阳区",
        incident_at="2026-05-28 20:10:00",
        incident_address="北京市北京市朝阳区世纪大道街道和丰大厦附近",
        appeal_purpose="依法查处",
        attachments=["购物小票.jpg"],
    ),
    # 高情绪投诉样例：核心字段基本齐全，但情绪等级应偏高，调解建议会提示优先安抚。
    Ticket(
        title="投诉餐饮店拒绝退款且态度恶劣",
        content=(
            "在北京市朝阳区体育西路街道青年西路某餐饮店充值会员卡500元，商家停业后无法消费，"
            "联系负责人一直拖延退款。本人非常生气，多次沟通无果，要求尽快退还余额。"
        ),
        ticket_no="DEMO-TICKET-003",
        ticket_type="民生服务->消费纠纷",
        contact_phone="demo-phone-003",
        customer_name="李女士",
        created_at="2026-05-29 15:30:00",
        due_at="2026-06-13 18:00:00",
        region="北京市朝阳区",
        incident_address="北京市北京市朝阳区体育西路街道青年西路109号附近",
        appeal_purpose="退款",
    ),
    # 明显非市场监管职责样例：夜间施工噪音通常建议退单或转其他部门。
    Ticket(
        title="反映小区夜间施工噪音扰民",
        content="北京市朝阳区桃园路附近工地连续多日夜间施工，噪音很大，影响休息，要求处理。",
        ticket_no="DEMO-TICKET-004",
        ticket_type="城市管理->噪音扰民",
        contact_phone="demo-phone-004",
        customer_name="王先生",
        created_at="2026-05-30 08:15:00",
        due_at="2026-06-14 18:00:00",
        region="北京市朝阳区",
        incident_at="2026-05-29 23:30:00",
        incident_address="北京市北京市朝阳区青年中路附近",
        appeal_purpose="要求制止夜间施工",
    ),
    # 职业索赔风险样例：只做风险提示，不影响普通工单处理；本条故意缺事发地址。
    Ticket(
        title="举报网店标签违法并要求十倍赔偿",
        content=(
            "本人近期已多次购买不同店铺食品进行维权。本次在北京市朝阳区某食品网店购买糕点，"
            "发现标签配料表不规范，依据食品安全法第一百四十八条要求十倍赔偿，"
            "如不处理将继续投诉举报。"
        ),
        ticket_no="DEMO-TICKET-005",
        ticket_type="民生服务->食品安全",
        contact_phone="demo-phone-005",
        #customer_name="赵某",
        created_at="2026-05-30 11:00:00",
        due_at="2026-06-14 18:00:00",
        region="北京市朝阳区",
        incident_at="2026-05-27 10:00:00",
        #incident_address="北京市北京市朝阳区某食品网店",
        appeal_purpose="十倍赔偿并依法查处",
        appeal_count=18,
        attachments=["商品标签.jpg", "订单截图.jpg"],
    ),
    # 多个核心字段缺失样例：应进入待补充或自动加入补充核心字段任务表。
    Ticket(
        title="投诉网购食品质量问题但信息不完整",
        content=(
            "消费者反映在网上购买食品后怀疑存在质量问题，要求退款处理。"
            "工单未提供具体商家名称、联系电话、事发地址和消费时间，需要工作人员进一步核实。"
        ),
        ticket_no="DEMO-TICKET-006",
        ticket_type="民生服务->消费纠纷",
        customer_name="匿名",
        created_at="2026-05-31 10:00:00",
        due_at="2026-06-15 18:00:00",
        appeal_purpose="退款",
    ),
    # 无法判断投诉/举报样例：文本只有模糊求助，不足以判断性质，适合演示低置信度人工确认。
    Ticket(
        title="咨询商家处理问题",
        content="来电人表示之前和一家店沟通过，但没有说明购买了什么商品，也没有说明具体争议，只希望有人联系解释一下。",
        ticket_no="DEMO-TICKET-007",
        ticket_type="民生服务->咨询求助",
        contact_phone="demo-phone-007",
        customer_name="陈先生",
        created_at="2026-06-01 09:00:00",
        due_at="2026-06-16 18:00:00",
        region="北京市朝阳区",
        incident_address="北京市北京市朝阳区",
        appeal_purpose="咨询解释",
    ),
    # 全国不同地区样例：属于消费纠纷但不在本 demo 当前处理范围内。
    Ticket(
        title="投诉异地商家拒绝退款",
        content="消费者在外地某商场购买电器后发现质量问题，商家拒绝退货退款，要求协调处理。",
        ticket_no="DEMO-TICKET-008",
        ticket_type="民生服务->消费纠纷",
        contact_phone="demo-phone-008",
        customer_name="周女士",
        created_at="2026-06-01 10:30:00",
        due_at="2026-06-16 18:00:00",
        region="西安市",
        incident_at="2026-05-30 15:00:00",
        incident_address="江苏省西安市雁塔区某商场",
        appeal_purpose="退款退货",
    ),
    # 材料和对象过少的举报样例：不能直接退单，应进入补充核心字段流程。
    Ticket(
        title="举报有人卖假货",
        content="提交人称网上看到有人卖假货，但未提供商家名称、链接、地址、交易记录或具体商品信息，要求查处。",
        ticket_no="DEMO-TICKET-009",
        ticket_type="民生服务->市场监管",
        contact_phone="demo-phone-009",
        customer_name="匿名",
        created_at="2026-06-01 14:00:00",
        due_at="2026-06-16 18:00:00",
        region="北京市朝阳区",
        appeal_purpose="查处",
    ),
    # 职责边界样例：涉及物业收费，通常不属于市场监管主责，适合演示建议退单。
    Ticket(
        title="投诉物业乱收停车费",
        content="小区物业突然提高停车费且拒绝解释，业主认为收费不合理，要求市场监管部门处理物业收费问题。",
        ticket_no="DEMO-TICKET-010",
        ticket_type="民生服务->物业服务",
        contact_phone="demo-phone-010",
        customer_name="刘xx",
        created_at="2026-06-02 08:30:00",
        due_at="2026-06-17 18:00:00",
        region="北京市朝阳区",
        incident_at="2026-06-01 19:00:00",
        incident_address="北京市北京市朝阳区某小区",
        appeal_purpose="要求处理收费",
    ),
    Ticket(
        title="举报企业长期未开业或连续停业",
        content="提交人反映，北京市北京市朝阳区某商业楼内的某企业管理有限公司自登记成立后，长期未实际开展经营活动，涉嫌成立后无正当理由超过六个月未开业；另据周边商户反映，该单位即使曾短暂开业，也已自行停业连续六个月以上。提交人要求市场监管部门依法核查该单位经营状态，并对涉嫌违法行为进行查处。",
        ticket_no="DEMO-TICKET-011",
        ticket_type="市场监管->企业监管",
        contact_phone="demo-phone-002",
        customer_name="张先生",
        created_at="2026-06-08 09:00:00",
        due_at="2026-06-23 18:00:00",
        region="北京市朝阳区",
        incident_at="2026-06-08 08:50:00",
        incident_address="北京市北京市朝阳区南大街某商业楼",
        appeal_purpose="要求依法核查并查处长期未开业或连续停业行为",
    )
]
"""模拟接口返回的工单列表，覆盖投诉、举报、无法判断、未知辖区、退单、字段缺失和职业索赔风险。"""
