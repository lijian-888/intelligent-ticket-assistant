"""Anonymized mock ticket data used before a real ticket system API is available."""

from app.models import Ticket


MOCK_TICKETS: list[Ticket] = [
    Ticket(
        title="投诉医疗器械用品虚假宣传并要求赔偿",
        content=(
            "提交人通过网络平台在某医疗器械用品店购买护理用品，订单号DEMO-ORDER-001，"
            "页面宣传具有明显治疗功效，但商品标识仅为普通企业执行标准。提交人认为存在虚假宣传，"
            "要求协调赔偿并核查宣传内容。"
        ),
        ticket_no="DEMO-TICKET-001",
        ticket_type="民生服务->权益保障",
        contact_phone="demo-phone-001",
        customer_name="匿名提交人A",
        created_at="2026-05-28 13:49:09",
        due_at="2026-06-10 12:00:32",
        region="北京市朝阳区",
        incident_at="2026-05-28 13:48:00",
        incident_address="北京市朝阳区建国路某商业综合体",
        third_party_ticket_no="DEMO-THIRD-PARTY-001",
        attachments=["订单截图.jpg", "商品宣传页.jpg"],
    ),
    Ticket(
        title="举报便利店销售过期食品",
        content=(
            "提交人在上海市浦东新区某便利店购买酸奶后发现已经超过保质期，"
            "店内货架仍摆放同批次过期食品，要求市场监管部门依法查处并反馈处理结果。"
        ),
        ticket_no="DEMO-TICKET-002",
        ticket_type="民生服务->食品安全",
        contact_phone="demo-phone-002",
        customer_name="匿名提交人B",
        created_at="2026-05-29 09:00:12",
        due_at="2026-06-12 18:00:00",
        region="上海市浦东新区",
        incident_at="2026-05-28 20:10:00",
        incident_address="上海市浦东新区世纪大道附近某便利店",
        appeal_purpose="依法查处",
        attachments=["购物小票.jpg"],
    ),
    Ticket(
        title="投诉餐饮店拒绝退款且态度恶劣",
        content=(
            "提交人在广州市天河区某餐饮店充值会员卡500元，商家停业后无法继续消费，"
            "联系负责人一直拖延退款。提交人表示非常生气，多次沟通无果，要求尽快退还余额。"
        ),
        ticket_no="DEMO-TICKET-003",
        ticket_type="民生服务->消费纠纷",
        contact_phone="demo-phone-003",
        customer_name="匿名提交人C",
        created_at="2026-05-29 15:30:00",
        due_at="2026-06-13 18:00:00",
        region="广东省广州市天河区",
        incident_address="广东省广州市天河区体育西路附近某餐饮店",
        appeal_purpose="退款",
    ),
    Ticket(
        title="反映小区夜间施工噪音扰民",
        content="提交人反映成都市武侯区某小区附近工地连续多日夜间施工，噪音较大，影响休息，要求处理。",
        ticket_no="DEMO-TICKET-004",
        ticket_type="城市管理->噪音扰民",
        contact_phone="demo-phone-004",
        customer_name="匿名提交人D",
        created_at="2026-05-30 08:15:00",
        due_at="2026-06-14 18:00:00",
        region="四川省成都市武侯区",
        incident_at="2026-05-29 23:30:00",
        incident_address="四川省成都市武侯区人民南路附近",
        appeal_purpose="要求制止夜间施工",
    ),
    Ticket(
        title="举报网店食品标签违法并要求十倍赔偿",
        content=(
            "提交人近期多次购买不同店铺食品进行维权。本次在杭州市西湖区某食品网店购买糕点，"
            "发现标签配料表不规范，依据食品安全法第一百四十八条要求十倍赔偿，"
            "如不处理将继续投诉举报。"
        ),
        ticket_no="DEMO-TICKET-005",
        ticket_type="民生服务->食品安全",
        contact_phone="demo-phone-005",
        created_at="2026-05-30 11:00:00",
        due_at="2026-06-14 18:00:00",
        region="浙江省杭州市西湖区",
        incident_at="2026-05-27 10:00:00",
        appeal_purpose="十倍赔偿并依法查处",
        appeal_count=18,
        attachments=["商品标签.jpg", "订单截图.jpg"],
    ),
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
    Ticket(
        title="咨询商家处理问题",
        content="来电人表示之前和一家店沟通过，但没有说明购买了什么商品，也没有说明具体争议，只希望有人联系解释一下。",
        ticket_no="DEMO-TICKET-007",
        ticket_type="民生服务->咨询求助",
        contact_phone="demo-phone-007",
        customer_name="匿名提交人E",
        created_at="2026-06-01 09:00:00",
        due_at="2026-06-16 18:00:00",
        region="湖北省武汉市江汉区",
        incident_address="湖北省武汉市江汉区",
        appeal_purpose="咨询解释",
    ),
    Ticket(
        title="投诉异地商家拒绝退款",
        content="消费者在西安市雁塔区某商场购买电器后发现质量问题，商家拒绝退货退款，要求协调处理。",
        ticket_no="DEMO-TICKET-008",
        ticket_type="民生服务->消费纠纷",
        contact_phone="demo-phone-008",
        customer_name="匿名提交人F",
        created_at="2026-06-01 10:30:00",
        due_at="2026-06-16 18:00:00",
        region="陕西省西安市雁塔区",
        incident_at="2026-05-30 15:00:00",
        incident_address="陕西省西安市雁塔区科技路附近某商场",
        appeal_purpose="退款退货",
    ),
    Ticket(
        title="举报有人销售假冒商品",
        content="提交人称在网络平台看到有人销售假冒商品，但未提供商家名称、链接、地址、交易记录或具体商品信息，要求查处。",
        ticket_no="DEMO-TICKET-009",
        ticket_type="民生服务->市场监管",
        contact_phone="demo-phone-009",
        customer_name="匿名",
        created_at="2026-06-01 14:00:00",
        due_at="2026-06-16 18:00:00",
        region="江苏省南京市玄武区",
        appeal_purpose="查处",
    ),
    Ticket(
        title="投诉物业乱收停车费",
        content="某小区物业突然提高停车费且拒绝解释，业主认为收费不合理，要求市场监管部门处理物业收费问题。",
        ticket_no="DEMO-TICKET-010",
        ticket_type="民生服务->物业服务",
        contact_phone="demo-phone-010",
        customer_name="匿名提交人G",
        created_at="2026-06-02 08:30:00",
        due_at="2026-06-17 18:00:00",
        region="重庆市渝北区",
        incident_at="2026-06-01 19:00:00",
        incident_address="重庆市渝北区某住宅小区",
        appeal_purpose="要求处理收费",
    ),
    Ticket(
        title="举报企业长期未开业或连续停业",
        content=(
            "提交人反映，某企业管理有限公司自登记成立后长期未实际开展经营活动，"
            "涉嫌成立后无正当理由超过六个月未开业；另据周边商户反映，该单位即使曾短暂开业，"
            "也已自行停业连续六个月以上。提交人要求市场监管部门依法核查经营状态并处理。"
        ),
        ticket_no="DEMO-TICKET-011",
        ticket_type="市场监管->企业监管",
        contact_phone="demo-phone-011",
        customer_name="匿名提交人H",
        created_at="2026-06-08 09:00:00",
        due_at="2026-06-23 18:00:00",
        region="福建省厦门市思明区",
        incident_at="2026-06-08 08:50:00",
        incident_address="福建省厦门市思明区某商务楼",
        appeal_purpose="要求依法核查并查处长期未开业或连续停业行为",
    ),
    Ticket(
        title="举报托管机构无证经营并提供餐饮服务",
        content=(
            "提交人反映，某托管机构现有从业人员3名，其中1名厨师，在未取得营业证照和食品经营许可证的情况下，"
            "对外招收学生提供托管服务和餐饮服务。检查时共有在托学生18名。"
            "提交人要求市场监管部门依法核查其无证无照经营和食品经营许可情况。"
        ),
        ticket_no="DEMO-TICKET-012",
        ticket_type="市场监管->食品经营许可",
        contact_phone="demo-phone-012",
        customer_name="匿名提交人I",
        created_at="2026-06-08 10:00:00",
        due_at="2026-06-23 18:00:00",
        region="山东省青岛市市南区",
        incident_at="2026-06-08 09:40:00",
        incident_address="山东省青岛市市南区某托管机构",
        appeal_purpose="要求依法核查并查处无证无照经营和未取得食品经营许可行为",
    ),
    Ticket(
        title="举报企业登记时提交虚假住所材料",
        content=(
            "提交人反映，某公司在企业登记平台申请营业执照时承诺填报信息和提交材料真实、准确、有效、完整，"
            "但该公司实际未与出租方签订房屋租赁合同，却上传疑似伪造的不动产权材料办理营业执照。"
            "提交人要求市场监管部门依法核查涉嫌提交虚假材料取得市场主体登记的行为。"
        ),
        ticket_no="DEMO-TICKET-013",
        ticket_type="市场监管->企业登记监管",
        contact_phone="demo-phone-013",
        customer_name="匿名提交人J",
        created_at="2026-06-08 11:00:00",
        due_at="2026-06-23 18:00:00",
        region="河南省郑州市金水区",
        incident_at="2024-07-04 09:00:00",
        incident_address="河南省郑州市金水区某企业登记住所",
        appeal_purpose="要求依法核查并处理提交虚假材料取得营业执照行为",
    ),
]
"""全国泛化模拟工单，覆盖投诉、举报、无法判断、退单、字段缺失和职业索赔风险。"""
