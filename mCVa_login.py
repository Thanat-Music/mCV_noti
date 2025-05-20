from mcv_ import CVaScraper
import requests
import re

mcv = CVaScraper()
# mcv._update_session_headers(mcv.auth_token)
def query_assignment(semester = 1, year = 2023, filter ="ALL"):
    """Query assignment data from Courseville API."""
    playload = {
        "query":"query AssignmentSummaryPageQuery($semester: String! $year: String! $filter: AssignmentFilter!) {...AssignmentSummaryFragment_bZQ9B}\
                fragment AssignmentSummaryFragment_bZQ9B on Query {\
                me {myCoursesBySemester(semester: $semester, year: $year) \
                {\
                    student {\
                        courseID title courseNumber courseYear thumbnail semester assignments(filter: $filter) \
                            {courseID id title type status outDate dueDate}}}}}",
        "variables":{"semester":semester,"year":year,"filter":filter}
        }
    headers = {'Authorization': f'Bearer {mcv.auth_token}',
            'Content-Type': 'application/json',
            'Content-Length': str(CVaScraper.get_body_length(playload))}

    data_res = mcv.session.post("https://api.alpha.mycourseville.com/query",headers=headers,json=playload)
    if data_res.status_code == 200:
        return data_res.json()
    else:
        raise Exception(f"!!!ALERT!!! Error: {data_res.status_code} \n text: {data_res.text}")
query_assignment(semester = 1, year = 2023, filter ="ALL")




