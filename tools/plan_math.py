"""Small CPM/PERT calculator for the documented preliminary plan.

Forward pass: ES=max(predecessor EF), EF=ES+duration.
Backward pass: LF=min(successor LS), LS=LF-duration; float=LS-ES.
Durations are working-day assumptions, not measured elapsed time. Unknown IDs,
cycles and invalid durations fail instead of producing a plausible schedule.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def calculate(plan):
    tasks = {row['id']: dict(row) for row in plan['tasks']}
    if len(tasks) != len(plan['tasks']):
        raise ValueError('Duplicate activity ID')
    order = []
    waiting = set(tasks)
    while waiting:
        ready = [key for key in tasks if key in waiting and
                 all(dep in order for dep in tasks[key]['predecessors'])]
        if not ready:
            raise ValueError('Cycle or unknown predecessor in schedule')
        for key in ready:
            task = tasks[key]
            if not isinstance(task['days'], (int, float)) or task['days'] <= 0:
                raise ValueError('Working-day duration must be positive')
            task['es'] = max((tasks[p]['ef'] for p in task['predecessors']), default=0)
            task['ef'] = task['es'] + task['days']
            order.append(key)
            waiting.remove(key)
    finish = max(task['ef'] for task in tasks.values())
    for key in reversed(order):
        successors = [row for row in tasks.values() if key in row['predecessors']]
        tasks[key]['lf'] = min((row['ls'] for row in successors), default=finish)
        tasks[key]['ls'] = tasks[key]['lf'] - tasks[key]['days']
        tasks[key]['float'] = tasks[key]['ls'] - tasks[key]['es']
    pert = plan['pert_example']
    o, m, p = (pert[key] for key in ['optimistic_hours','most_likely_hours','pessimistic_hours'])
    if not 0 <= o <= m <= p:
        raise ValueError('PERT requires 0 <= optimistic <= likely <= pessimistic')
    return {'tasks': [tasks[row['id']] for row in plan['tasks']],
            'finish_days': finish, 'buffer_days': plan['buffer_days'],
            'buffered_days': finish + plan['buffer_days'],
            'critical': [key for key in order if tasks[key]['float'] == 0],
            'pert_hours': (o + 4*m + p)/6, 'pert_sigma_hours': (p-o)/6}


if __name__ == '__main__':
    print(json.dumps(calculate(json.loads((ROOT/'team/core-schedule.json').read_text())), ensure_ascii=False, indent=2))
