import requests

res = requests.post("http://192.168.1.49:5000/create_user", json={
    "username": "chebien1",
    "password": "123456",
    "full_name": "Nguyễn Văn A",
    "department": "chebien",
    "role": "nhanvien"
})

print(res.json())
