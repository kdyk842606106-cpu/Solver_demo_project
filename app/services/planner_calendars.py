"""Weekly project calendars; immutable elapsed-minute expansion per run."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def periods(value):
    if not isinstance(value, list):
        raise ValueError('工作时段必须为列表')
    result = []
    for p in value:
        if not isinstance(p, dict) or set(p) != {'start', 'end'}:
            raise ValueError('时段需要 start/end')
        nums = []
        for key in ('start', 'end'):
            t = p[key]
            if not isinstance(t, str) or len(t) != 5 or t[2] != ':':
                raise ValueError('时段必须使用 HH:MM')
            h, m = map(int, t.split(':'))
            if not (0 <= h <= 24 and 0 <= m < 60) or (h == 24 and m != 0):
                raise ValueError('工作时段时间无效')
            nums.append(h*60+m)
        if nums[0] >= nums[1]:
            raise ValueError('时段结束必须晚于开始；跨午夜班次请拆成两个日期内时段')
        result.append(tuple(nums))
    result.sort()
    if any(a[1] > b[0] for a,b in zip(result,result[1:])):
        raise ValueError('工作时段不能重叠')
    return result


def validate_calendars(s):
    rule=s.get('night_lift_rule')
    if rule is not None:
        if not isinstance(rule,dict) or set(rule)!={'enabled','night_start','night_end'} or type(rule['enabled']) is not bool:
            raise ValueError('夜班吊装规则需要 enabled/night_start/night_end')
        # First release supports an overnight night shift, with one daylight block.
        try:
            periods([{'start':rule['night_end'],'end':rule['night_start']}])
        except (ValueError,TypeError) as exc:
            raise ValueError('夜班须为跨午夜时段，例如20:00–次日08:00') from exc
        if rule['night_start']=='24:00':
            raise ValueError('夜班开始请使用00:00–23:59，且夜班必须跨午夜')
    calendars = s.get('work_calendars', [])
    if not isinstance(calendars, list) or len(calendars) > 100:
        raise ValueError('工作日历必须为列表，最多100个')
    ids = set()
    for c in calendars:
        if not isinstance(c, dict) or set(c) - {'id','name','weekdays','periods','exceptions'}:
            raise ValueError('工作日历结构不支持')
        if not isinstance(c.get('id'),str) or not c['id'] or c['id'] in ids:
            raise ValueError('工作日历ID缺失或重复')
        ids.add(c['id'])
        if not isinstance(c.get('name'),str) or not c['name'].strip():
            raise ValueError('请输入日历名称')
        days = c.get('weekdays')
        if not isinstance(days,list) or not days or any(type(d) is not int or not 0<=d<=6 for d in days) or len(days)!=len(set(days)):
            raise ValueError('每周至少选择一个工作日，周一为0、周日为6')
        if not periods(c.get('periods')):
            raise ValueError('每周至少配置一个工作时段')
        exceptions = c.get('exceptions', [])
        if not isinstance(exceptions,list) or len(exceptions)>1000:
            raise ValueError('日期例外最多1000条')
        dates=set()
        for e in exceptions:
            if not isinstance(e,dict) or set(e) != {'date','periods'}:
                raise ValueError('日期例外需要 date/periods')
            day=date.fromisoformat(e['date'])
            if day.isoformat()!=e['date'] or day in dates:
                raise ValueError('例外日期无效或重复')
            dates.add(day)
            periods(e['periods'])
    if s.get('work_calendar_id') is not None and s['work_calendar_id'] not in ids:
        raise ValueError('所选工作日历不存在；请先切换日历再删除')


def calendar_intervals(s):
    validate_calendars(s)
    cid=s.get('work_calendar_id')
    night=night_rule_enabled(s)
    if not cid and not night:
        return []
    c=next(c for c in s['work_calendars'] if c['id']==cid) if cid else {
        'weekdays':list(range(7)),'periods':[{'start':'00:00','end':'24:00'}],'exceptions':[]}
    context=s.get('calendar_context') or {}
    try:
        anchor=datetime.fromisoformat(context['start_at'].replace('Z','+00:00'))
        zone=ZoneInfo(context['timezone'])
    except (KeyError,ValueError) as exc:
        raise ValueError('工作日历求解需要带时区的计划开始时间') from exc
    if anchor.tzinfo is None or anchor.second or anchor.microsecond:
        raise ValueError('日历计划开始时间必须带时区且精确到整分钟')
    anchor=anchor.astimezone(timezone.utc)
    t0=s.get('start_time',0)
    from app.services.planner_scenarios import expand_packages
    active=expand_packages(s)
    release=max([t0,*[e['time'] for e in s.get('external_events',[])],
                 *[w['earliest_start'] for w in active.get('time_windows',[])],
                 *[w['earliest_start'] for w in active.get('run_time_windows',[]) if w.get('earliest_start') is not None]])
    workload=s['max_steps']*max([1,*[a['duration'] for a in active.get('activities',[])]])
    exceptions={e['date']:periods(e['periods']) for e in c.get('exceptions',[])}
    weekly=periods(c['periods'])
    current=anchor.astimezone(zone).date()
    result=[]
    remaining=workload
    restricted=restricted_lifts(active) if night else []
    daylight=periods([{'start':s['night_lift_rule']['night_end'],'end':s['night_lift_rule']['night_start']}])[0] if night else (0,1440)
    weekly_day_work=sum(max(0,min(b,daylight[1])-max(a,daylight[0])) for a,b in weekly)
    recurring=[a for a in restricted if a['duration']<=weekly_day_work]
    largest=max([0,*[a['duration'] for a in recurring]])
    # After finite exceptions and the ordinary worst-case work budget, reserve
    # one full weekly cycle per possible restricted occurrence. Each recurring
    # feasible activity fits at least one of those days; never truncate proofs
    # merely because mandatory daylight waiting exceeds the old work horizon.
    needed_days=7*min(s['max_steps'],sum(min(s['max_steps'],a.get('max_instances') or s['max_steps']) for a in restricted)) if largest else 0
    last_exception=max([current,*[date.fromisoformat(d) for d in exceptions]]) if restricted else current

    def offset(day, minute):
        wall=datetime.combine(day,time())+timedelta(minutes=minute)
        local=wall.replace(tzinfo=zone)
        if local.utcoffset()!=wall.replace(tzinfo=zone,fold=1).utcoffset() or local.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)!=wall:
            raise ValueError('工作时段边界遇到夏令时歧义或不存在的本地时间，请调整时段')
        seconds=(local.astimezone(timezone.utc)-anchor).total_seconds()
        if seconds%60:
            raise ValueError('该时区偏移不支持整数分钟排程')
        return t0+int(seconds//60)

    # Explicit implementation limit: never report this as mathematical infeasibility.
    for _ in range(3660):
        daily=exceptions.get(current.isoformat(), weekly if current.weekday() in c['weekdays'] else [])
        eligible=current>=last_exception and offset(current,0)>=release
        if needed_days and eligible and remaining<=0:
            needed_days-=1
        for a,b in daily:
            start,end=max(t0,offset(current,a)),offset(current,b)
            if end<=start:
                continue
            if result and result[-1][1]==start:
                result[-1][1]=end
            else:
                result.append([start,end])
            if not restricted or current>=last_exception:
                remaining-=max(0,end-max(start,release))
        if remaining<=0 and needed_days<=0 and current>=last_exception:
            return result
        current+=timedelta(days=1)
    raise ValueError('日历展开超过10年支持范围，请缩小场景执行范围')


def night_rule_enabled(s):
    return bool((s.get('night_lift_rule') or {}).get('enabled'))


def restricted_lifts(s):
    cranes={r['id'] for r in s.get('resources',[]) if r.get('kind')=='crane'}
    return [a for a in s.get('activities',[]) if a.get('is_active',True)
            and (a.get('metadata') or {}).get('precision_fragile') is True
            and any(rid in cranes and qty>0 for rid,qty in a.get('resource_reqs',{}).items())]


def lift_day_windows(s, working):
    if not night_rule_enabled(s):
        return {}
    validate_calendars(s)
    anchor=datetime.fromisoformat(s['calendar_context']['start_at'].replace('Z','+00:00')).astimezone(timezone.utc)
    zone=ZoneInfo(s['calendar_context']['timezone'])
    t0=s.get('start_time',0)
    start,end=periods([{'start':s['night_lift_rule']['night_end'],'end':s['night_lift_rule']['night_start']}])[0]
    day=anchor.astimezone(zone).date()
    last=(anchor+timedelta(minutes=working[-1][1]-t0)).astimezone(zone).date()
    windows=[]
    while day<=last:
        edges=[]
        for minute in (start,end):
            wall=datetime.combine(day,time())+timedelta(minutes=minute)
            local=wall.replace(tzinfo=zone)
            if local.utcoffset()!=wall.replace(tzinfo=zone,fold=1).utcoffset() or local.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)!=wall:
                raise ValueError('夜班边界遇到夏令时歧义，请调整时段')
            edges.append(t0+int((local.astimezone(timezone.utc)-anchor).total_seconds()/60))
        left,right=max(t0,edges[0]),min(working[-1][1],edges[1])
        if left<right:
            windows.append([left,right])
        day+=timedelta(days=1)
    from app.services.planner_scenarios import expand_packages
    return {a['id']:windows for a in restricted_lifts(expand_packages(s))}
