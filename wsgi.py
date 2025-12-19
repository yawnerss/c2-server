services:
  - type: web
    name: c2-web-control
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python server.py
    envVars:
      - key: PORT
        value: 10000
      - key: PYTHON_VERSION
        value: 3.9.0
