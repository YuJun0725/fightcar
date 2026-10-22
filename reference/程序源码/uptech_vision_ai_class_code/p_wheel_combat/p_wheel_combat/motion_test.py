from motion_controller import MotionController
import time

motion = MotionController()

print("Default Pose")
motion.default_platform()
time.sleep(3.0)

print("Ahead Platform")
motion.go_up_ahead_platform()
time.sleep(3.0)

print("Behind Platform")
motion.go_up_behind_platform()
time.sleep(3.0)

print("Test Test")