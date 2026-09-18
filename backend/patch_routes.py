with open("app/api/routes/grouping.py", "r") as f:
    content = f.read()

content = content.replace("GenerateGroupsRequest, MoveStudentRequest", "GenerateGroupsRequest, MoveStudentRequest, UpdateGroupRequest")

new_route = """
@router.patch("/sessions/{session_id}/groups/{group_id}", response_model=GroupingResponse)
def update_group(session_id: UUID, group_id: UUID, req: UpdateGroupRequest, db: Session = Depends(get_db)):
    svc = GroupingService(db)
    return svc.update_group(session_id, group_id, req)
"""

content += new_route

with open("app/api/routes/grouping.py", "w") as f:
    f.write(content)
