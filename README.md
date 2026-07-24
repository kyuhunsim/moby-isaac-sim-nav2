# Moby Isaac Sim + Nav2

Neuromeka Moby mobile manipulator를 NVIDIA Isaac Sim과 ROS 2 Nav2로 실행하기 위한
최소 구성입니다.

현재 기본 stage는 `moby_simple_room_final.usd`이며, warehouse 실험·MPPI/DWB 비교·3D
costmap 기록 기능은 포함하지 않습니다. 사람 이동은 Isaac Sim stage 실행 시 선택할 수
있는 동적 장애물 기능으로만 제공합니다.

## 지원 기준

- Ubuntu 22.04
- ROS 2 Humble
- NVIDIA Isaac Sim 5.1.0
- Python 3.10 계열

## 폴더 구조

```text
src/
├── isaac_moby_description/   # Moby base + Indy RP2 URDF/mesh
├── isaac_moby_sim/           # Isaac Sim USD와 stage runner
├── isaac_moby_controller/    # /cmd_vel -> /joint_command
└── isaac_moby_navigation/    # Nav2, simple-room map, RViz
```

## 준비

```bash
cd /home/rise/moby-isaac-nav2
source /opt/ros/humble/setup.zsh
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.zsh
```

만약 system Python의 `setuptools`가 61 미만이라는 오류가 나오면, 현재 개발
환경에서는 다음처럼 호환 setuptools 경로를 추가해 빌드합니다.

```bash
PYTHONNOUSERSITE=1 \
PYTHONPATH=/home/rise/miniconda3/envs/isaaclab311/lib/python3.11/site-packages \
colcon build --symlink-install
```

## 기본 실행

Terminal 1:

```bash
cd /home/rise/moby-isaac-nav2
source /opt/ros/humble/setup.zsh
export ISAAC_SIM_ROOT=/home/rise/isaac-sim_5.1.0
# Isaac Sim uses its own Python; avoid leaking an active conda interpreter.
unset CONDA_PREFIX CONDA_DEFAULT_ENV CONDA_PROMPT_MODIFIER

$ISAAC_SIM_ROOT/python.sh \
  src/isaac_moby_sim/scripts/run_moby_stage.py \
  --source-usd src/isaac_moby_sim/assets/scenes/moby_simple_room_final.usd
```

Terminal 2:

```bash
cd /home/rise/moby-isaac-nav2
source /opt/ros/humble/setup.zsh
source install/setup.zsh
ros2 run isaac_moby_controller moby_joint_commander
```

Terminal 3:

```bash
cd /home/rise/moby-isaac-nav2
source /opt/ros/humble/setup.zsh
source install/setup.zsh

ros2 launch isaac_moby_navigation navigation.launch.py \
  use_sim_time:=true \
  use_rviz:=true
```

## 사람 이동

기본 simple-room USD에는 Isaac People용 `/World/Characters/Character`가 들어 있지
않습니다. 따라서 `kinematic` 모드에서는 실행기가 `/World/People/Person`에 보이는
캡슐 proxy를 만들고 지정한 경로를 따라 이동시킵니다. 실제 Isaac People 캐릭터가
포함된 stage를 사용할 때만 `people` 모드를 선택합니다.

사람 경로는 `src/isaac_moby_sim/config/people_scenarios.json`에서 관리하거나 CLI에서
직접 지정합니다. 좌표는 최종 simple-room USD 기준의 월드 좌표입니다.

```bash
$ISAAC_SIM_ROOT/python.sh \
  src/isaac_moby_sim/scripts/run_moby_stage.py \
  --source-usd src/isaac_moby_sim/assets/scenes/moby_simple_room_final.usd \
  --people-motion-mode=kinematic \
  --people-speed-mps=0.5 \
  --people-waypoint=0.0,0.0,0.0 \
  --people-waypoint=1.0,0.0,0.0 \
  --people-start-at-first-waypoint \
  --people-loops=inf
```

## Asset 출처

- `src/isaac_moby_sim/assets/scenes/moby_simple_room_final.usd`: Isaac Sim 5.1.0 USD folder
- `src/isaac_moby_sim/assets/arm/indy_rp2_v2.usd`: mobile manipulator USD share
- `src/isaac_moby_description/urdf/moby.urdf`: Moby URDF source
- `src/isaac_moby_description/model/meshes/`: Moby and Indy mesh files

USD/mesh asset의 재배포 가능 여부와 외부 reference는 공개 전 확인해야 합니다.
