
import re
import json
import requests
import datetime
from bs4 import BeautifulSoup

vin_not_found_error_msg = "Vin not found error."


def is_error_in_response(result):

    if result.status_code in [500]:
        return True, 'internal server error in maker site.'

    result = result.text.lower()

    if "error retrieving recall" in result:
        return True, "error retrieving recall"

    if "read timed out executing" in result:
        return True, "read timed out executing"

    if "service unavailable" in result:
        return True, "service unavailable"

    if "unable to tunnel through proxy" in result:
        return True, "unable to tunnel through proxy"

    if "could not extract response" in result:
        return True, "could not extract response"

    if "failure to fetch the Recall data" in result:
        return True, "failure to fetch the recall data"

    if "forbidden" in result:
        return True, "forbidden"

    if 'the vin entered appears not to be working properly.' in result or 'VEHICLE_INVALID_VIN'.lower() in result or \
            'This is not a recognized Nissan VIN'.lower() in result or \
            'The VIN entered is not a recognized vehicle in our system.'.lower() in result:
        return True, vin_not_found_error_msg

    return False, ''


session = requests.session()
session.headers.update(
    {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/79.0.3945.117 Safari/537.36'
     }
)


def get_result(url_):
    timer = 10
    while timer > 0:
        timer -= 1
        try:
            return session.get(url_, timeout=20, verify=True)
        except Exception as ex:
            print(ex)


class RecallSpider:
    def __init__(self, make, vin):
        self.make = make
        self.vin = vin
        self.err_list_js = None
        self.nissan_state = ''
        self.nissan_state_mac = ''
        self.nissan_state_version = ''

    def get_results(self):
        items = {
            "Car Name": self.make,
            "Vin Number": self.vin,
            "incomplete_recalls": 0,
            "response_status_from_company_site": 200
        }

        if self.make.lower() in ['chrysler', 'dodge', 'jeep', 'ram']:
            url = ("https://www.mopar.com/moparsvc/recallInfo?vin={}&mrkt=ca&language=en_ca&campaign_status=All"
                   "&campaign_type=A&callback=showVinInfo").format(self.vin.strip())

            res = get_result(url)
            items['response_status_from_company_site'] = res.status_code
            js = res.text.replace("showVinInfo(", "").replace("]}}]})", "]}}]}") \
                .replace("}}]})", "}}]}").replace('}]})', '}]}')

            js = json.loads(js)

            if 'vehicle' in js['vin_recall'][0]:
                vehicle = js['vin_recall'][0]['vehicle']
                name = '{} {}'.format(vehicle['model_year'], vehicle['vehicle_desc'])
                items['Car'] = name
                count = 0
                if 'recall_details' in js['vin_recall'][0]:
                    for x in js['vin_recall'][0]['recall_details']['recall']:
                        repair_date = x['repair_date']
                        if datetime.datetime.strptime(repair_date, '%Y-%m-%d') > datetime.datetime.today():
                            count += 1
                            row_out = {
                                "Recall Type {}".format(count): x['type_of_campaign'],
                                "Recall Status {}".format(count): x['vin_campaign_status'],
                                "Recall Title {}".format(count): x['campaign_desc'],
                                "Description {}".format(count): x['condition_and_risk']
                            }
                            items.update(row_out)

                    items["incomplete_recalls"] = count
            elif js['vin_recall'][0]['vin_status_desc'] == 'Invalid VIN':
                items['Message'] = vin_not_found_error_msg
            else:
                items['Message'] = js['vin_recall'][0]['vin_status_desc']
                
        elif self.make.lower(
        ) in ['chevrolet', 'buick', 'gmc', 'cadillac', 'pontiac', 'oldsmobile', 'saturn', 'hummer', 'saab']:

            url = 'https://my.gm.ca/cms/read/all/gm/ca/en?callback=gm.cmsPrefetchHandler&maxTextLength=400'
            res = get_result(url)

            error, error_msg = is_error_in_response(res)

            if error:
                items['Message'] = error_msg

            self.err_list_js = res.text.replace('"}])', '"}]').replace('gm.cmsPrefetchHandler(', '')
            self.err_list_js = json.loads(self.err_list_js)

            url = "https://my.gm.ca/gm/en/api/{}/recalls?cb=".format(self.vin.strip())
            res = get_result(url)

            items['response_status_from_company_site'] = res.status_code
            error, error_msg = is_error_in_response(res)
            if error:
                items['Message'] = error_msg
            else:
                js = json.loads(res.text)
                count = 0

                if not js['data']:
                    error = js['Messages'][0]
                    items['Message'] = error
                else:
                    items = {
                        "Car Name": self.make,
                        "Vin Number": self.vin,
                        "Car": '{} {} {}'.format(js['data']['year'], js['data']['make'], js['data']['model']),
                        "incomplete_recalls": 0,
                    }

                    for x in js['data']['recalls']:
                        row_out = {}
                        count += 1

                        status = [y['elementValue'] for y in self.err_list_js if y['elementId'] ==
                                  'recallCenter_recallsFound_recalls_status_{}'.format(x['mfr_recall_status'])][0]
                        type_ = x['recall_type']
                        title = x['recall_title']
                        desc = x['recall_description']
                        row_out["Recall Type {}".format(count)] = type_
                        row_out["Recall Status {}".format(count)] = status
                        row_out["Recall Title {}".format(count)] = title
                        row_out["Description {}".format(count)] = desc

                        items.update(row_out)

                    items["incomplete_recalls"] = count

        elif self.make.lower() in ['ford']:
            url = ('https://www.digitalservices.ford.com/sharedServices/recalls/query.do?vin={}&country=USA'
                   '&langscript=LATN&language=EN&region=US').format(self.vin.strip())
            print(url)
            res = get_result(url)
            items['response_status_from_company_site'] = res.status_code
            if "input parameter invalid".lower() in res.text.lower():
                items['Message'] = "Input parameter invalid"

            error, error_msg = is_error_in_response(res)

            if error:
                items['Message'] = error_msg
            else:
                js = json.loads(res.text)
                name = None
                if 'nhtsa_header_details' in js:
                    name = '{} {}'.format(js['nhtsa_header_details']['year'], js['nhtsa_header_details']['model'])

                items["Car"] = name

                if 'recalls' in js:
                    count = 0
                    for x in js['recalls']['nhtsa_recall_item']:
                        count += 1
                        row_out = {
                            "Recall Type {}".format(count): 'Safety',
                            "Recall Status {}".format(count): x['mfr_recall_status'],
                            "Recall Title {}".format(count): x['description_eng'],
                            "Description {}".format(count): x['recall_description']
                        }

                        items.update(row_out)

                if not name:
                    url = 'https://www.digitalservices.ford.com/sharedServices/decodevin.do?vin={}'.format(self.vin)
                    res = get_result(url)
                    error, error_msg = is_error_in_response(res)

                    if error:
                        items['Message'] = error_msg
                    else:
                        js = json.loads(res.text)
                        name = '{} {}'.format(js['decodedVin']['modelYear']['attributeValue'],
                                              js['decodedVin']['model']['attributeValue'])
                        items["Car"] = name

        elif self.make.lower() in ['honda']:
            url = 'https://www.honda.ca/recalls/{}'.format(self.vin.strip())
            print(url)
            res = get_result(url)
            items['response_status_from_company_site'] = res.status_code

            error, error_msg = is_error_in_response(res)
            if error:
                items['Message'] = error_msg
            else:
                count = 0
                soup = BeautifulSoup(res.content, "html.parser")
                for recall in soup.findAll('span', id=re.compile('^BodyContent_RightColumn_ContentArea_RightColumn_'
                                                                 'ContentArea_gvRecallNotifications_lblTitle')):
                    recall = recall.text.strip()
                    d = recall.split(':')

                    if len(d) > 1:
                        type_ = d[0].strip('Recall').strip()
                        title = d[1].strip()
                    else:
                        title = d[0].strip()
                        type_ = ''

                    count += 1
                    row_out = {
                        "Recall Type {}".format(count): type_,
                        "Recall Status {}".format(count): 'Incomplete',
                        "Recall Title {}".format(count): title,
                        "Description {}".format(count): ''
                    }
                    items.update(row_out)

                items['incomplete_recalls'] = count

        elif self.make.lower() in ['hyundai']:
            url = 'https://www.hyundaicanada.com/en/owners-section/recalls?VIN={}'.format(self.vin.strip())
            print(url)
            res = get_result(url)

            items['response_status_from_company_site'] = res.status_code
            error, error_msg = is_error_in_response(res)

            if error:
                items['Message'] = error_msg
            else:
                soup = BeautifulSoup(res.content, "html.parser")
                count = 0
                name = soup.select('h3[class="op-vehicle-recalls__model"]')[0].text

                for recall in soup.select('div[class="op-safety-recalls__accordion-content collapse"]'):
                    title = recall.select('h4[class^="op-safety-recalls__accordion-content-heading"]')[0].text
                    desc = recall.select('p[class^="op-safety-recalls__accordion-content-description"]')[0].text
                    status = recall.select('p[class^="op-safety-recalls__accordion-content-status"]'
                                           )[0].text.replace('Recalls Status :', '').strip()
                    items['Car'] = name

                    if 'incomplete' in status.lower():
                        count += 1
                        row_out = {
                            "Recall Type {}".format(count): '',
                            "Recall Status {}".format(count): status,
                            "Recall Title {}".format(count): title,
                            "Description {}".format(count): desc
                        }
                        items.update(row_out)

                items['incomplete_recalls'] = count

        elif self.make.lower() in ['toyota']:
            url = 'https://www.toyota.ca/toyota/RecallsByVin'
            res = get_result(url)
            # error, error_msg = is_error_in_response(res)
            #
            # if error:
            #     items['Message'] = error_msg
            # else:
            items['response_status_from_company_site'] = None
            items['Message'] = 'Scraper not implemented for toyota.'

        elif self.make.lower() in ['nissan']:
            url = "https://nna.secure.force.com/support/ContactUsNissan?recallLookup"
            res = get_result(url)

            error, error_msg = is_error_in_response(res)
            if error:
                items['Message'] = error_msg

            else:
                soup = BeautifulSoup(res.content, "html.parser")

                nissan_state = soup.find("input", {"name": "com.salesforce.visualforce.ViewState"})['value'].replace(
                    ':', '%3A').replace('/', '%2F').replace('+', '%2B').replace('=', '%3D')

                nissan_state_mac = soup.find("input", {"name": "com.salesforce.visualforce.ViewStateMAC"})[
                    'value'].replace(':', '%3A').replace('/', '%2F').replace('+', '%2B').replace('=', '%3D')

                nissan_state_version = soup.find("input", {"name": "com.salesforce.visualforce.ViewStateVersion"})[
                    'value'].replace(':', '%3A').replace('/', '%2F').replace('+', '%2B').replace('=', '%3D')

                url = 'https://nna.secure.force.com/support/ContactUsNissan'

                res = session.post(
                    url=url,
                    headers={
                        "Accept": "*/*",
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                        "Sec-Fetch-Site": "same-origin",
                        "Sec-Fetch-Mode": "cors",
                        "Connection": "keep-alive",
                        "Origin": "https://nna.secure.force.com",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Sec-Fetch-Dest": "empty",
                        'Accept-Encoding': 'gzip, deflate, br'
                    },
                    data="AJAXREQUEST=_viewRoot"
                    "&j_id0:form=j_id0:form"
                    "&j_id0:form:userBrowser=Chrome"
                    "&j_id0:form:userBrowserVersion=80.0.3987.116"
                    "&j_id0:form:recallLookupVin={}"
                    "&com.salesforce.visualforce.ViewState={}"
                    "&com.salesforce.visualforce.ViewStateVersion={}"
                    "&com.salesforce.visualforce.ViewStateMAC={}"
                    "&j_id0:form:searchRecallButton=j_id0:form:searchRecallButton"  # 1N4AL3AP7EN238386
                    "&".format(self.vin, nissan_state, nissan_state_version, nissan_state_mac)
                )

                items['response_status_from_company_site'] = res.status_code

                error, error_msg = is_error_in_response(res)

                if error:
                    items['Message'] = error_msg
                else:
                    soup = BeautifulSoup(res.content, "html.parser")

                    items["Car"] = soup.select(
                        "div[class=row] > div[class='col-md-12 col-sm-12 col-xs-12'] > p[style='font-family: "
                        "nissan_brand_bold; color: #999999; font-size: 2em;']")[0].text

                    count = 0
                    for x in soup.select(
                            "div[class='col-md-12 col-sm-12 col-xs-12'] > div[style='border-bottom-style: solid; border"
                            "-bottom-color: #F2F2F2; background-color:#FAFAFA; padding: 10px;'], div[style='border-"
                            "bottom-style: solid; border-bottom-color: #F2F2F2; background-color:#FFFFFF; padding: "
                            "10px;']"):
                        title = x.select('p')[0].text.strip()
                        print(title)
                        date = x.select('p')[1].text.split(':')[-1].strip()
                        print(date)
                        row_out = {}
                        count += 1
                        row_out["Recall Type {}".format(count)] = ''
                        row_out["Recall Status {}".format(count)] = ''
                        row_out["Recall Title {}".format(count)] = title
                        row_out["Description {}".format(count)] = ''

                        items.update(row_out)
                    items['incomplete_recalls'] = count

        else:
            items["response_status_from_company_site"] = None
            items["Message"] = 'no maker matched to the name.'

        return items
