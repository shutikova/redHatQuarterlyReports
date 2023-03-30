import json

from django.shortcuts import render
from urllib.parse import quote
from traceback import format_exc
from generateReport.models import Quarter, Team
from generateReport.create_report import create_report

configuration = json.load(open("resources/configuration.json"))


def index(request):
    context = {
        "quarters_list": Quarter.objects.order_by("-quarter_text"),
        "teams_list": Team.objects.order_by("-team_text"),
        "email": configuration["contact_email"],
    }

    return render(request, "generateReport/generate_report.html", context)


def results(request):
    wp = float(request.POST.get("wp"))
    relop = float(request.POST.get("relop"))
    maint = float(request.POST.get("maint"))
    stand = float(request.POST.get("stand"))
    up = float(request.POST.get("up"))
    sup = float(request.POST.get("sup"))
    other = float(request.POST.get("other"))
    team = request.POST.get("team")
    quarter = request.POST.get("quarter")

    team_text = Team.objects.filter(id=team).first().team_text
    quarter_text = Quarter.objects.filter(id=quarter).first().quarter_text
    quarter_start = Quarter.objects.filter(id=quarter).first().quarter_start
    quarter_end = Quarter.objects.filter(id=quarter).first().quarter_end

    try:
        url = create_report(
            team_text,
            quarter_text,
            quarter_start,
            quarter_end,
            [wp, relop, maint, stand, up, sup, other],
        )
        context = {"url": url, "email": configuration["contact_email"]}
        return render(request, "generateReport/generated_report.html", context)

    except Exception:
        context = {
            "error_message": quote(format_exc()),
            "subject": quote("Error occurred in quarterly reporting tool"),
            "email": configuration["contact_email"],
        }
        return render(request, "generateReport/error.html", context)
