"""提醒技能——mock 实现"""
def execute(params: dict) -> dict:
    title = params.get('title', '提醒')
    time_str = params.get('time', '5分钟后')
    return {'status': 'ok', 'reminder_id': 'rem_001', 'message': f'已设置提醒: {title} 在 {time_str}'}
