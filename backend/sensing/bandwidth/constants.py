"""Named domain values for the WP-3B-02 bandwidth budget block (`06` §2.9/§3.10).

The bandwidth *formula* and its cap live in `backend.camera.constants` and are
imported, never restated here — two sources of truth for `W×H×Bpp×8×fps` is the
outcome this WP most needs to avoid. What this module names is the material the
block layer adds on top: the `lsusb -t` tree tokens that recover the per-controller
grouping (FR-CAM-005), the two operations a breach refuses, the fixed length of the
mitigation ladder (FR-CAM-012/013), and the RealSense timeout symptom whose two
causes must both be reported (FR-CAM-071).
"""

from __future__ import annotations

# The USB device class `lsusb -t` prints for a UVC camera interface. A RealSense
# also exposes its streams through Video-class interfaces, so this is the marker
# for "a camera hangs here" when reading the tree. It is used only to *list* the
# camera-class nodes of a parsed topology for a report; the budget itself sums
# descriptors, so a missed class name degrades the report, never the block.
CAMERA_USB_CLASS = "Video"

# The class string a root hub carries; each root hub is one USB controller, and a
# controller is the unit FR-CAM-005 budgets shared bandwidth against.
ROOT_HUB_CLASS = "root_hub"

# Controller identity rendered from a bus number, matching the Linux `usbN` device
# name so a parsed controller reads the same as the sysfs node an operator would see.
CONTROLLER_ID_PREFIX = "usb"

# The two operations the block refuses when a configuration exceeds budget
# (FR-CAM-011: refuse both save and start — a block, not a warning).
ACTION_SAVE = "save"
ACTION_START = "start"

# The mitigation ladder is a fixed five rungs (`06` §5 Q7 / `02b` WP-3C-01 five-step ladder).
# Naming the count keeps the acceptance check ("five steps offered") from hard-coding 5.
MITIGATION_STEP_COUNT = 5

# The RealSense error whose diagnosis this WP fixes: it is reported for *both* a
# bandwidth breach and a bus-power shortfall, and naming only one cause sends the
# operator down the wrong remedy (`02b` WP-3B-02 ④, FR-CAM-071).
FRAME_TIMEOUT_SYMPTOM = "Frame did not arrive in time"

# The two independent causes the symptom above maps to.
CAUSE_BANDWIDTH = "bandwidth"
CAUSE_POWER = "power"
