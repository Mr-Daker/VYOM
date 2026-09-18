with open("app/services/gap_detection_service.py", "r") as f:
    content = f.read()

content = content.replace("warnings = list(set(warnings))", "warnings = sorted(list(set(warnings)))")

with open("app/services/gap_detection_service.py", "w") as f:
    f.write(content)
