# api/index.py
from flask import Flask, request, jsonify, send_from_directory
import json, re, os, traceback
from datetime import datetime
import requests
from requests.auth import HTTPBasicAuth
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# === SECURE CONFIG (from Vercel Environment Variables) ===
HA_WEBHOOK_URL = os.getenv("HA_WEBHOOK_URL", "http://sidmsmith.zapto.org:8123/api/webhook/manhattan_app_usage")
HA_HEADERS = {"Content-Type": "application/json"}

AUTH_HOST = os.getenv("MANHATTAN_AUTH_HOST", "salep-auth.sce.manh.com")
API_HOST = os.getenv("MANHATTAN_API_HOST", "salep.sce.manh.com")
USERNAME_BASE = os.getenv("MANHATTAN_USERNAME_BASE", "sdtadmin@")
PASSWORD = os.getenv("MANHATTAN_PASSWORD")
CLIENT_ID = os.getenv("MANHATTAN_CLIENT_ID", "omnicomponent.1.0.0")
CLIENT_SECRET = os.getenv("MANHATTAN_SECRET")

# Critical: Fail fast if secrets missing
if not PASSWORD or not CLIENT_SECRET:
    raise Exception("Missing MANHATTAN_PASSWORD or MANHATTAN_SECRET environment variables")

STATUS_MAP = {
    "1000": "Requested", "2000": "Countered", "3000": "Scheduled",
    "4000": "Checked In", "8000": "Complete", "9000": "Cancelled"
}

# === HELPERS ===
def send_ha_message(payload):
    try:
        requests.post(HA_WEBHOOK_URL, json=payload, headers=HA_HEADERS, timeout=5)
    except:
        pass

def get_manhattan_token(org):
    url = f"https://{AUTH_HOST}/oauth/token"
    username = f"{USERNAME_BASE}{org.lower()}"
    data = {
        "grant_type": "password",
        "username": username,
        "password": PASSWORD,
    }
    auth = HTTPBasicAuth(CLIENT_ID, CLIENT_SECRET)
    try:
        r = requests.post(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            auth=auth,
            timeout=30,
            verify=False,
        )
        r.raise_for_status()
        return r.json().get("access_token")
    except:
        return None

def check_in_trailer(appt_data, headers, org):
    url = f"https://{API_HOST}/yard-management/api/yard-management/transaction/trailer/checkIn"
    headers = headers.copy()
    headers.update({
        "Content-Type": "application/json",
        "selectedOrganization": org,
        "selectedLocation": f"{org}-DM1"
    })
    appt_type = appt_data.get("AppointmentTypeId", "")
    trailer_info = {
        "CarrierId": appt_data.get("CarrierId"),
        "TrailerId": appt_data.get("TrailerId"),
        "EquipmentTypeId": appt_data.get("EquipmentTypeId")
    }
    # Include ConditionCodeId if provided
    condition_code = appt_data.get("ConditionCodeId")
    if condition_code:
        trailer_info["ConditionCodeId"] = condition_code

    payload = {
        "AppointmentInfo": {
            "AppointmentId": appt_data.get("AppointmentId"),
            "AppointmentTypeId": appt_type
        },
        "VisitType": appt_type,
        "TrailerInfo": trailer_info
    }
    
    # TODO: Add validation for ASN and Shipment if specified on appointment
    # If appt_data contains ASN (e.g., appt_data.get("ASN") or appt_data.get("AsnId")),
    # validate that the ASN exists in the system using the appropriate API endpoint.
    # If appt_data contains Shipment (e.g., appt_data.get("ShipmentId") or appt_data.get("Shipment")),
    # validate that the Shipment exists in the system using the appropriate API endpoint.
    # Return an error response if validation fails before proceeding with check-in.
    
    # Log the request payload (raw JSON)
    try:
        payload_json = json.dumps(payload, indent=2)
        print(f"[CHECK-IN REQUEST] URL: {url}")
        print(f"[CHECK-IN REQUEST] Organization: {org}")
        print(f"[CHECK-IN REQUEST] Appointment ID: {appt_data.get('AppointmentId')}")
        print(f"[CHECK-IN REQUEST] Raw JSON Payload Sent:")
        print(payload_json)
    except Exception as log_err:
        print(f"[CHECK-IN REQUEST] Error logging payload: {str(log_err)}")
        print(f"[CHECK-IN REQUEST] Payload (fallback): {payload}")
    
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=30, verify=False)
        
        # Log the full response details
        print(f"[CHECK-IN RESPONSE] Status Code: {r.status_code}")
        print(f"[CHECK-IN RESPONSE] Response Headers: {dict(r.headers)}")
        print(f"[CHECK-IN RESPONSE] Raw Response Text (first 5000 chars):")
        print(r.text[:5000])
        
        try:
            response_json = r.json()
            print(f"[CHECK-IN RESPONSE] Parsed JSON Response:")
            print(json.dumps(response_json, indent=2))
        except Exception as json_err:
            print(f"[CHECK-IN RESPONSE] Failed to parse JSON: {str(json_err)}")
            response_json = {"raw_text": r.text[:2000]}

        if r.ok and response_json.get("success"):
            msg_list = response_json.get("messages", {}).get("Message", [])
            description = next((m.get("Description") for m in msg_list if m.get("Description")), "Check-in successful")
            print(f"[CHECK-IN SUCCESS] Message: {description}")
            return {"success": True, "message": description}
        else:
            # Log failure details
            print(f"[CHECK-IN FAILURE] Status OK: {r.ok}, Success in JSON: {response_json.get('success')}")
            err_list = response_json.get("errors", []) or response_json.get("exceptions", [])
            err_msg = err_list[0].get("message") if err_list else "Unknown error"
            print(f"[CHECK-IN FAILURE] Error Message: {err_msg}")
            print(f"[CHECK-IN FAILURE] Full Error Details:")
            print(json.dumps(response_json, indent=2))
            return {"success": False, "error": err_msg}
    except Exception as e:
        # Log exception with full traceback
        print(f"[CHECK-IN EXCEPTION] Request failed with exception:")
        print(f"[CHECK-IN EXCEPTION] Exception Type: {type(e).__name__}")
        print(f"[CHECK-IN EXCEPTION] Exception Message: {str(e)}")
        print(f"[CHECK-IN EXCEPTION] Full Traceback:")
        print(traceback.format_exc())
        return {"success": False, "error": f"Request failed: {str(e)}"}

def format_date(date_str):
    if not date_str:
        return "—"
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%m/%d %I:%M %p").lstrip("0")
    except:
        return "—"

def format_status(status_id):
    return STATUS_MAP.get(status_id, "Unknown")

# === API ROUTES ===
@app.route('/api/app_opened', methods=['POST'])
def app_opened():
    # Track app opened event (metadata will be added by frontend)
    return jsonify({"success": True})

@app.route('/api/ha-track', methods=['POST'])
def ha_track():
    """Track events to Home Assistant webhook"""
    try:
        data = request.json
        event_name = data.get('event_name')
        metadata = data.get('metadata', {})
        
        # Build complete payload with app info and timestamp
        payload = {
            "event_name": event_name,
            "app_name": "check-in",
            "app_version": "0.1.0",
            **metadata,
            "timestamp": datetime.now().isoformat()
        }
        
        send_ha_message(payload)
        return jsonify({"success": True})
    except Exception as e:
        # Silently fail - don't interrupt user experience
        print(f"[HA] Failed to track event: {e}")
        return jsonify({"success": True})  # Return success anyway

@app.route('/api/auth', methods=['POST'])
def auth():
    org = request.json.get('org', '').strip()
    if not org:
        return jsonify({"success": False, "error": "ORG required"})
    token = get_manhattan_token(org)
    if token:
        return jsonify({"success": True, "token": token})
    return jsonify({"success": False, "error": "Auth failed"})

@app.route('/api/scheduled', methods=['POST'])
def scheduled():
    """Fetch all scheduled (non-checked-in) appointments"""
    org = request.json.get('org')
    token = request.json.get('token')
    if not all([org, token]):
        return jsonify({"success": False, "error": "Missing data"})

    url = f"https://{API_HOST}/appointment/api/appointment/appointment/search"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "selectedOrganization": org,
        "selectedLocation": f"{org}-DM1"
    }
    # Paginate through all results
    all_appointments = []
    page = 0
    page_size = 1000
    try:
        while True:
            payload = {
                "Query": "AppointmentStatusId= 3000",
                "Template": {
                    "AppointmentId": None,
                    "ArrivalDateTime": None
                },
                "Size": page_size,
                "Page": page
            }
            r = requests.post(url, json=payload, headers=headers, timeout=30, verify=False)
            if not r.ok:
                return jsonify({"success": False, "error": "Failed to fetch scheduled appointments"})
            data = r.json().get("data", [])
            all_appointments.extend(data)
            # If fewer results than page size, we've got them all
            if len(data) < page_size:
                break
            page += 1
        return jsonify({"success": True, "appointments": all_appointments})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/search', methods=['POST'])
def search():
    """Search for a specific appointment by AppointmentId"""
    org = request.json.get('org')
    appointment_id = request.json.get('appointment_id', '').strip()
    token = request.json.get('token')
    if not all([org, appointment_id, token]):
        return jsonify({"success": False, "error": "Missing data"})

    url = f"https://{API_HOST}/appointment/api/appointment/appointment/search"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "selectedOrganization": org,
        "selectedLocation": f"{org}-DM1"
    }
    payload = {
        "Query": f"AppointmentId = '{appointment_id}'",
        "Size": 1,
        "Page": 0
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=30, verify=False)
        results = r.json().get("data", []) if r.ok else []
    except:
        results = []

    for appt in results:
        appt['ScheduledDate'] = format_date(appt.get('PreferredDateTime'))
        appt['StatusText'] = format_status(appt.get('AppointmentStatusId'))

    return jsonify({
        "success": True,
        "results": results
    })

@app.route('/api/condition_codes', methods=['POST'])
def condition_codes():
    """Fetch trailer condition codes"""
    org = request.json.get('org')
    token = request.json.get('token')
    if not all([org, token]):
        return jsonify({"success": False, "error": "Missing data"})

    url = f"https://{API_HOST}/yard-management/api/yard-management/trailerConditionCode/search"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "selectedOrganization": org,
        "selectedLocation": f"{org}-DM1"
    }
    payload = {
        "Query": "",
        "Size": 9999,
        "needTotalCount": True,
        "Template": {
            "ConditionCodeId": None,
            "Description": None,
            "RemoveCurrentLocation": None
        }
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=30, verify=False)
        if r.ok:
            data = r.json().get("data", {})
            codes = data.get("TrailerConditionCode", [])
            return jsonify({"success": True, "codes": codes})
        else:
            return jsonify({"success": False, "error": "Failed to fetch condition codes"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/checkin', methods=['POST'])
def checkin():
    appt = request.json.get('appt')
    org = request.json.get('org')
    token = request.json.get('token')
    if not all([appt, org, token]):
        return jsonify({"success": False, "error": "Missing data"})

    headers = {"Authorization": f"Bearer {token}"}
    result = check_in_trailer(appt, headers, org)
    return jsonify(result)


@app.route('/api/upload_signature', methods=['POST'])
def upload_signature():
    """Upload driver signature to Manhattan Document Manager for each ASN/PO"""
    data = request.json
    org = data.get('org')
    token = data.get('token')
    object_type_id = data.get('objectTypeId')  # "ASN" or "PurchaseOrder"
    object_id = data.get('objectId')
    filename = data.get('filename')
    file_data = data.get('fileData')  # Base64 encoded PNG
    notes = data.get('notes', '')

    if not all([org, token, object_type_id, object_id, filename, file_data]):
        return jsonify({"success": False, "error": "Missing required fields"})

    url = f"https://{API_HOST}/document-manager/api/document-manager/uploadDocuments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "selectedOrganization": org.upper(),
        "selectedLocation": f"{org.upper()}-DM1"
    }
    payload = {
        "ObjectTypeId": object_type_id,
        "ObjectId": object_id,
        "DocumentCategoryId": "DriverSignature",
        "Action": "overWrite",
        "Description": "Uploaded via Check-In Kiosk",
        "DocumentManagerFiles": [{
            "FileName": filename,
            "DocumentName": "Driver Signature",
            "Description": "Driver signature captured during check-in",
            "Notes": notes,
            "FileData": file_data
        }]
    }

    try:
        print(f"[SIGNATURE UPLOAD] {object_type_id}: {object_id}, File: {filename}")
        r = requests.post(url, json=payload, headers=headers, timeout=30, verify=False)
        print(f"[SIGNATURE UPLOAD] Status: {r.status_code}")
        print(f"[SIGNATURE UPLOAD] Response: {r.text[:2000]}")

        if r.ok:
            try:
                res_json = r.json()
                if res_json.get("success") is False:
                    err_list = res_json.get("errors", []) or res_json.get("exceptions", [])
                    err_msg = err_list[0].get("message") if err_list else "Upload failed"
                    return jsonify({"success": False, "error": err_msg})
            except:
                pass
            return jsonify({"success": True, "message": f"Signature uploaded for {object_type_id} {object_id}"})
        else:
            return jsonify({"success": False, "error": f"Upload failed (HTTP {r.status_code})"})
    except Exception as e:
        print(f"[SIGNATURE UPLOAD] Exception: {str(e)}")
        return jsonify({"success": False, "error": str(e)})


# === FALLBACK: Serve index.html for SPA (Critical for Vercel) ===
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_static(path):
    if path.startswith('api/'):
        return "API route not found", 404
    # Don't serve index.html for JavaScript files that don't exist - return 404 instead
    if path.endswith('.js'):
        return jsonify({'error': 'File not found'}), 404
    try:
        return send_from_directory('..', 'index.html')
    except:
        return "File not found", 404

# === DEV SERVER ===
if __name__ == '__main__':
    app.run(port=5000, debug=True)