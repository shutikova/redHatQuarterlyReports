import json
import gspread
import webcolors

import pandas as pd

from gspread_formatting import set_column_width
from gspread_dataframe import set_with_dataframe
from jira import JIRA, exceptions, resources
from typing import List, Optional
from generateReport.create_charts import create_pie_chart, create_bar_chart

configuration = json.load(open("resources/configuration.json"))


def authorisation() -> Optional[JIRA]:
    token = configuration["token"]
    jira = JIRA(server="https://issues.redhat.com/", token_auth=token)
    jira.myself()
    return jira


def get_wp(jira: JIRA, team: str, quarter: str, quarter_start: str, quarter_end: str)\
        -> Optional[List[resources.Issue]]:
    jql_request = (
        f"project={team} and issueFunction in issuesInEpics('project={team} and issuetype=Epic and "
        f"fixVersion in ({quarter})') and resolved >= '{quarter_start}'"
        f"AND resolved < '{quarter_end}' AND 'Story Points' is not EMPTY"
    )
    return jira.search_issues(jql_request, maxResults=10000)


def get_release_operations(jira: JIRA, team: str, quarter_start: str, quarter_end: str)\
        -> Optional[List[resources.Issue]]:
    jql_request1 = (
        f"project={team} AND issuetype not in (Ticket, Sub-task, Epic) AND "
        f"EXD-WorkType = 'Release Operations' AND EXD-WorkType not in ('Maintenance') "
        f"AND resolved >= '{quarter_start}' AND resolved < '"
        f"{quarter_end}' AND 'Epic Link' is EMPTY AND 'Story Points' is not EMPTY"
    )

    jql_request2 = (
        f"project={team} AND issuetype not in (Ticket, Sub-task, Epic) "
        f"AND resolved >= '{quarter_start}' AND resolved < "
        f"'{quarter_end}' AND issueFunction in linkedIssuesOf(\"issuetype = 'Release Milestone'\", 'is parent of')"
        f" AND 'Story Points' is not EMPTY"
    )
    return jira.search_issues(jql_request1, maxResults=10000) + jira.search_issues(
        jql_request2, maxResults=10000
    )


def get_maintenance(jira: JIRA, team: str, quarter_start: str, quarter_end: str)\
        -> Optional[List[resources.Issue]]:
    jql_request = (
        f"project={team} AND issuetype not in (Ticket, Sub-task, Epic) AND "
        f"EXD-WorkType not in ('Release Operations') AND EXD-WorkType = "
        f"'Maintenance' AND resolved >= '{quarter_start}' AND resolved < '"
        f"{quarter_end}' AND 'Epic Link' is EMPTY AND 'Story Points' is not EMPTY"
    )
    return jira.search_issues(jql_request, maxResults=10000)


def get_standalone(
    jira: JIRA, team: str, quarter_start: str, quarter_end: str
) -> Optional[List[resources.Issue]]:
    jql_request = (
        f"project={team} AND issuetype not in (Ticket, Sub-task, Epic) AND "
        f"(EXD-WorkType not in ('Release Operations', 'Maintenance') "
        f"OR EXD-WorkType is EMPTY) AND resolved >= '{quarter_start}' "
        f"AND resolved < '{quarter_end}' AND 'Epic Link' is EMPTY "
        f"AND 'Story Points' is not EMPTY"
    )
    return jira.search_issues(jql_request, maxResults=10000)


def get_issues_with_multiple_work_type(
    jira: JIRA, team: str, quarter_start: str, quarter_end: str
) -> Optional[List[resources.Issue]]:
    jql_request = (
        f"project={team} AND issuetype not in (Ticket, Sub-task, Epic) AND "
        f"((EXD-WorkType = 'Release Operations' AND EXD-WorkType = "
        f"'Maintenance') OR (EXD-WorkType = 'Maintenance' AND EXD-WorkType = "
        f"'Release Operations')) AND resolved >= '{quarter_start}' AND resolved < '"
        f"{quarter_end}' AND 'Story Points' is not EMPTY"
    )
    return jira.search_issues(jql_request, maxResults=10000)


def get_issues_without_story_points(
    jira: JIRA, team: str, quarter_start: str, quarter_end: str
) -> Optional[List[resources.Issue]]:
    jql_request = (
        f"project={team} AND issuetype not in (Ticket, Sub-task, Epic) AND 'Story Points' is EMPTY "
        f"AND resolved >= '{quarter_start}' AND resolved <"
        f" '{quarter_end}' AND resolution not in "
        + "("
        + '"Can\'t Do"'
        + ", 'Cannot Reproduce', Duplicate, 'Duplicate Ticket', 'Not a Bug', "
        "Obsolete, Unresolved, " + '"Won\'t Do"' + ")"
    )
    return jira.search_issues(jql_request, maxResults=10000)


def get_story_points(issues: List[resources.Issue]) -> int:
    sp = 0
    for issue in issues:
        sp += int(issue.get_field(configuration["custom_fields"]["story_points"]))
    return sp


def count_ratios(metric: List[float], multiplier: float) -> List[float]:
    ratio = []
    total = sum(metric)
    for i in range(len(metric)):
        if metric[i] == 0 or multiplier == 0:
            ratio.append(0)
        else:
            ratio.append(round(metric[i] / total * multiplier, 2))
    return ratio


def count_final_fte(planned_ftes: List[float], ratio: List[float]) -> List[float]:
    ftes = []
    planned_total_ftes = sum(planned_ftes)
    for i in range(len(planned_ftes)):
        ftes.append(round(ratio[i] * planned_total_ftes, 2))
    return ftes


def comments(fte_difference: List[float]) -> List[str]:
    comm = []
    for i in fte_difference:
        if i > 0:
            comm.append(
                f"In reality, roughly {round(i, 2)} FTEs were working on this category; less than was planned"
            )
        elif i < 0:
            comm.append(
                f"In reality, roughly {round(i, 2)} FTEs were working on this category; more than was planned"
            )
        else:
            comm.append(
                f"In reality, roughly {round(i, 2)} FTEs were working on this category; same as was planned"
            )
    return comm


def create_google_sheet(team: str, quarter: str) -> gspread.Spreadsheet:
    service_account = gspread.service_account(filename="resources/service_account.json")
    sheet = service_account.create(quarter + " " + team, configuration["report_path"])
    sheet.add_worksheet("Report", rows=100, cols=20)
    sheet.del_worksheet(sheet.worksheet("Sheet1"))
    return sheet


def create_error_reports(
    sheet: gspread.Spreadsheet, issues: List[resources.Issue], name: str
) -> None:
    if issues:
        df = pd.DataFrame()
        df["Key"] = list(
            map(
                lambda x: f'=HYPERLINK("https://issues.redhat.com/browse/{str(x)}", '
                f'"{str(x)}")',
                issues,
            )
        )
        df["Issue name"] = list(map(lambda x: x.fields.summary, issues))
        df["Status"] = list(map(lambda x: x.fields.status, issues))
        df["Created"] = list(map(lambda x: x.fields.created[:10], issues))
        df["Reporter"] = list(map(lambda x: x.fields.reporter, issues))
        df["Assignee"] = list(map(lambda x: x.fields.assignee, issues))
        set_with_dataframe(sheet.add_worksheet(name, rows=10000, cols=1), df)


def create_report(
    team: str,
    quarter: str,
    quarter_start: str,
    quarter_end: str,
    planned_ftes: List[float],
) -> str:
    try:
        jira = authorisation()
    except exceptions.JIRAError:
        raise exceptions.JIRAError("Could not log in to Jira")

    try:
        sheet = create_google_sheet(team, quarter)
    except gspread.exceptions.APIError:
        raise gspread.exceptions.APIError("Error creating new spreadsheet")

    no_sp_issues = get_issues_without_story_points(
        jira, team, quarter_start, quarter_end
    )
    create_error_reports(sheet, no_sp_issues, "Issues without story points")

    multiple_exd_issues = get_issues_with_multiple_work_type(
        jira, team, quarter_start, quarter_end
    )
    create_error_reports(
        sheet, multiple_exd_issues, "Issues with multiple EXD-WorkType"
    )

    format_sheet(sheet)

    work_packages = get_wp(jira, team, quarter, quarter_start, quarter_end)
    release_operations = get_release_operations(jira, team, quarter_start, quarter_end)
    maintenance = get_maintenance(jira, team, quarter_start, quarter_end)
    standalone = get_standalone(jira, team, quarter_start, quarter_end)

    planned_ratio = count_ratios(planned_ftes, 1)
    final_sps = [
        get_story_points(work_packages),
        get_story_points(release_operations),
        get_story_points(maintenance),
        get_story_points(standalone),
    ]
    final_ratio = count_ratios(final_sps, sum(planned_ratio[:4])) + planned_ratio[4:]
    final_ftes = count_final_fte(planned_ftes, final_ratio)

    difference = [planned_ftes[i] - final_ftes[i] for i in range(7)]

    no_sp = ["This is not captured by the Story points", "", ""]

    df = pd.DataFrame(index=range(7))
    df["Total Available capacity"] = [
        "Change Portfolio",
        "Business As Usual",
        "",
        "",
        "",
        "",
        "",
    ]
    df[str(sum(planned_ftes))] = list(configuration["metrics_names"])
    df["Planned FTEs"] = [str(i) for i in planned_ftes]
    df["Planned capacity distribution"] = [str(i) for i in planned_ratio]
    df["Final FTEs"] = [str(i) for i in final_ftes]
    df["Final SPs"] = [str(i) for i in final_sps] + no_sp
    df["Final capacity distribution"] = [str(i) for i in final_ratio]
    df["Diff planned vs real"] = [str(i) for i in difference]
    df["Commentary"] = comments(difference)

    set_with_dataframe(sheet.worksheet("Report"), df)

    create_pie_chart(
        sheet.id,
        sheet.worksheet("Report").id,
        "Planned Capacity",
        [1, 2, 8, 3],
        [10, 0],
    )
    create_pie_chart(
        sheet.id, sheet.worksheet("Report").id, "Actual Capacity", [1, 4, 8, 5], [10, 2]
    )
    create_bar_chart(sheet.id, sheet.worksheet("Report").id)

    return sheet.url


def format_sheet(sheet: gspread.Spreadsheet) -> None:
    report_wsh = sheet.worksheet("Report")
    report_wsh.merge_cells("F6:F8")
    report_wsh.merge_cells("A3:A8")
    set_column_width(report_wsh, "A:H", 245)
    set_column_width(report_wsh, "I", 700)

    dark_grey = webcolors.hex_to_rgb(configuration["colors"]["dark_grey"])
    cell_style_dark_grey = {
        "backgroundColor": {
            "red": dark_grey[0] / 255,
            "green": dark_grey[1] / 255,
            "blue": dark_grey[2] / 255,
        },
        "textFormat": {"fontSize": 13, "bold": True},
    }

    light_grey = webcolors.hex_to_rgb(configuration["colors"]["light_grey"])
    cell_style_light_grey = {
        "backgroundColor": {
            "red": light_grey[0] / 255,
            "green": light_grey[1] / 255,
            "blue": light_grey[2] / 255,
        }
    }

    orange = webcolors.hex_to_rgb(configuration["colors"]["orange"])
    cell_style_orange = {
        "backgroundColor": {
            "red": orange[0] / 255,
            "green": orange[1] / 255,
            "blue": orange[2] / 255,
        }
    }

    light_orange = webcolors.hex_to_rgb(configuration["colors"]["light_orange"])
    cell_style_light_orange = {
        "backgroundColor": {
            "red": light_orange[0] / 255,
            "green": light_orange[1] / 255,
            "blue": light_orange[2] / 255,
        }
    }

    light_red = webcolors.hex_to_rgb(configuration["colors"]["light_red"])
    cell_style_light_red = {
        "backgroundColor": {
            "red": light_red[0] / 255,
            "green": light_red[1] / 255,
            "blue": light_red[2] / 255,
        }
    }

    properties = {
        "borders": {
            "top": {"style": "SOLID"},
            "bottom": {"style": "SOLID"},
            "left": {"style": "SOLID"},
            "right": {"style": "SOLID"},
        },
        "horizontalAlignment": "CENTER",
        "verticalAlignment": "middle",
    }

    report_wsh.format("A1:I8", properties)
    report_wsh.format("A1:A8", cell_style_dark_grey)
    report_wsh.format("B2:B8", cell_style_dark_grey)
    report_wsh.format("C1:I1", cell_style_dark_grey)
    report_wsh.format("C2:C8", cell_style_light_orange)
    report_wsh.format("B1", cell_style_light_orange)
    report_wsh.format("D2:D8", cell_style_orange)
    report_wsh.format("E2:G8", cell_style_light_grey)
    report_wsh.format("H2:I8", cell_style_light_red)

    try:
        no_sp = sheet.worksheet("Issues without story points")
        set_column_width(no_sp, "A:F", 200)
        set_column_width(no_sp, "B", 700)
        no_sp.format("A1:F1", cell_style_dark_grey)
        no_sp.format("A:F", properties)
    except gspread.exceptions.WorksheetNotFound:
        pass

    try:
        exd = sheet.worksheet("Issues with multiple EXD-WorkType")
        set_column_width(exd, "A:F", 200)
        set_column_width(exd, "B", 700)
        exd.format("A1:F1", cell_style_dark_grey)
        exd.format("A:F", properties)
    except gspread.exceptions.WorksheetNotFound:
        pass
