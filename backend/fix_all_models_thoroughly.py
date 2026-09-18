import re

with open("app/models/all_models.py", "r") as f:
    content = f.read()

# First, find the start of RotationPlan to split the file
idx = content.find('class RotationPlan(Base):')
if idx != -1:
    pre_rotation = content[:idx]
else:
    pre_rotation = content

# Clean pre_rotation of any CheckConstraints related to chk_rs or chk_rp
pre_rotation = re.sub(r"\s*CheckConstraint\('[^']*',\s*name='chk_rs_[^']*'\),?", "", pre_rotation)
pre_rotation = re.sub(r"\s*CheckConstraint\('[^']*',\s*name='chk_rp_[^']*'\),?", "", pre_rotation)

# Let's also check if there are multi-line check constraints left over
# The bad patch added these lines:
#         CheckConstraint('priority_score_snapshot >= 0 AND priority_score_snapshot <= 100', name='chk_rs_snapshot_score'),
#         CheckConstraint('algorithm_priority_rank_snapshot > 0', name='chk_rs_snapshot_algo_rank'),
#         ...
# The regex above will catch them since they are single lines.

with open("app/models/all_models.py", "w") as f:
    f.write(pre_rotation)

