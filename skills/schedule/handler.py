"""日程管理技能——mock 实现"""
def execute(params: dict) -> dict:
    action = params.get('action', 'list')
    if action == 'add':
        return {'status': 'ok', 'message': f'已添加日程: {params.get("title", "")} at {params.get("time", "")}'}
    return {'schedules': [{'title': '团队周会', 'time': '10:00'}, {'title': '午饭', 'time': '12:00'}], 'count': 2}
