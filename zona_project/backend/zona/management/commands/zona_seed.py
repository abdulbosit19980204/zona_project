from django.core.management.base import BaseCommand
from django.db import transaction

from zona.models import (Authority, ChangeRequest, Department, EdgeCase, Event, Member, Process, ProcessRole, System,
                         Task, TaskFallback, Team)
from zona.seed_data import (AUTHORITIES, DEPARTMENTS, EDGE_CASES, EXTRA_MEMBERS, FALLBACKS, MEMBER_DEPARTMENT,
                            MEMBER_TEAM, MEMBERS, PROCESS_ROLES, SYSTEMS, TASKS, TEAMS, TRIGGERS)


class Command(BaseCommand):
    help = "Namuna ma'lumotni (StarGroup IT) bo'sh bazaga yuklaydi; --reset hammasini qayta yozadi."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Mavjud ma'lumot va tarixni o'chirib, qayta yuklaydi")

    @transaction.atomic
    def handle(self, *args, **opts):
        if Member.objects.exists() and not opts["reset"]:
            self.stdout.write("Baza bo'sh emas, o'tkazib yuborildi (qayta yuklash uchun --reset).")
            return
        if opts["reset"]:
            for model in (ChangeRequest, Event, EdgeCase, Task, ProcessRole, Authority, Process, Member, Team,
                          Department, System):
                model.objects.all().delete()

        deps = {key: Department.objects.create(name=name, description=desc, order=i)
                for i, (key, name, desc) in enumerate(DEPARTMENTS)}
        teams = {key: Team.objects.create(department=deps[dep], name=name, description=desc, order=i)
                 for i, (key, dep, name, desc, _) in enumerate(TEAMS)}
        systems = {name: System.objects.create(name=name, order=i) for i, name in enumerate(SYSTEMS)}

        members = {}
        for i, m in enumerate(MEMBERS + EXTRA_MEMBERS):
            members[m["key"]] = Member.objects.create(
                name=m["name"], role=m["role"], is_team=m["is_team"], department=deps.get(MEMBER_DEPARTMENT.get(m["key"])),
                team=teams.get(MEMBER_TEAM.get(m["key"])),
                trigger=TRIGGERS.get(m["key"], ""), does=m["does"], excludes=m["excludes"], order=i)
        for key, _, _, _, lead in TEAMS:
            Team.objects.filter(pk=teams[key].pk).update(lead=members[lead])

        order = p_order = 0
        owned = {}  # xodim kaliti -> uning jarayonlari
        for key, groups in TASKS.items():
            for direction, system, items in groups:
                process = Process.objects.create(name=direction, system=systems[system], order=p_order)
                p_order += 1
                ProcessRole.objects.create(process=process, member=members[key], role=ProcessRole.OWNER)
                owned.setdefault(key, []).append(process)
                for title in items:
                    Task.objects.create(title=title, process=process, owner=members[key], order=order)
                    order += 1

        for member_key, role, of_key in PROCESS_ROLES:
            for process in owned.get(of_key, []):
                ProcessRole.objects.create(process=process, member=members[member_key], role=role)

        for i, (key, title, scope) in enumerate(AUTHORITIES):
            Authority.objects.create(member=members[key], title=title, scope=scope, order=i)

        for i, (situation, key, then) in enumerate(EDGE_CASES):
            EdgeCase.objects.create(situation=situation, first_owner=members[key], then_text=then, order=i)

        for title, first, chain in FALLBACKS:
            task = Task.objects.filter(title=title).first()
            if not task:
                continue
            Task.objects.filter(pk=task.pk).update(owner=members[first])
            for n, (key, condition) in enumerate(chain, start=2):
                TaskFallback.objects.create(task=task, member=members[key], condition=condition, order=n)

        if opts["verbosity"]:
            self.stdout.write(self.style.SUCCESS(
                f"Yuklandi: {Department.objects.count()} bo'lim, {Team.objects.count()} jamoa, {Member.objects.count()} xodim, "
                f"{Process.objects.count()} jarayon, {Task.objects.count()} vazifa, {EdgeCase.objects.count()} aralash holat."))
