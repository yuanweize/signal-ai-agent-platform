import urllib.request, json, subprocess
totp = subprocess.check_output(['docker', 'exec', 'smb-backend', 'python3', '-c', "import pyotp; print(pyotp.TOTP('N4TS56IHLBMMR6FYHX4TJ4ACDLDOODXI').now())"]).decode().strip()
req = urllib.request.Request("http://localhost:8000/api/auth/login", data=json.dumps({"username": "admin", "password": "3NB7B7BXYN7H6QI5SIOCGDKH5VXABCAF", "totp_code": totp}).encode(), headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req)
token = json.loads(resp.read())['access_token']
print("TOKEN:", token)
req2 = urllib.request.Request("http://localhost:8000/api/dashboard/stats", headers={"Authorization": f"Bearer {token}"})
print(urllib.request.urlopen(req2).read().decode())
