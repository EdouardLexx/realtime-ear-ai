# realtime-ear-ai
AI-powered Computer Vision project to calculate the percentage of eye opening (EAR) from facial landmarks detected by Mediapipe.

This code uses Mediapipe and Computer Vision to accurately estimate the eye openness percentage based on the Eye Aspect Ratio (EAR) metric.

💡 Overview

This Python project implements a robust solution for quantifying eye openness from an image. It leverages Mediapipe's Face Mesh model for highly precise facial landmark detection and applies the Eye Aspect Ratio (EAR) calculation to determine the "percentage of openness" for both the left and right eyes.

This technique is widely used in applications like drowsiness detection, attention monitoring, and human-computer interaction.

✨ Features

    Real-time Landmark Detection: Utilizes Mediapipe for high-fidelity detection of the 6 key facial landmarks surrounding each eye.

    Eye Aspect Ratio (EAR) Calculation: Implements the standard EAR formula to calculate the ratio of vertical to horizontal distances of the eye.

    Openness Percentage Quantification: Converts the raw EAR value into an intuitive percentage (0% for fully closed, 100% for fully open) using customizable thresholds (MAX_EAR and CLOSED_EYE_THRESHOLD).

    Visual Output: Renders the calculated landmarks on the image and displays the final percentage of openness directly on the screen using OpenCV.

    Debug Output: Prints detailed coordinate and calculation values (A, B, C distances) to the console for verification and analysis.

⚙️ Prerequisites

You need the following libraries to run the script:

    Python 3.x

    OpenCV (cv2)

    NumPy

    Mediapipe

You can install the necessary packages using pip:
Bash

pip install opencv-python numpy mediapipe

🚀 How to Run

    Clone the repository:
    Bash

git clone https://github.com/YourUsername/eye-openness-detection-ai.git
cd eye-openness-detection-ai

Update the image path:
Open the Python script and change the image_path variable to point to your image file:
Python

image_path = "path/to/your/image.jpg"

Execute the script:
Bash

    python your_script_name.py 

🛠️ Key Technical Details

EAR Calculation

The core logic resides in the eye_aspect_ratio function, which computes the EAR based on the Euclidean distances between the six eye landmarks (P1 to P6).
<img width="470" height="126" alt="image" src="https://github.com/user-attachments/assets/83c412fa-0d53-4ee6-9eae-55ebbda486fa" />

    ∥p2​−p6​∥ and ∥p3​−p5​∥ represent the vertical distances.

    ∥p1​−p4​∥ represents the horizontal distance (width).

Percentage Conversion

The raw EAR is converted to a percentage based on defined calibration values:
Constant	Value	Description
MAX_EAR	0.35	The EAR value considered as 100% open (can be tuned).
CLOSED_EYE_THRESHOLD	0.15	The EAR value below which the eye is considered 0% open.

The final percentage is calculated as: min(MAX_EAREAR​×100,100)

Here’s what you can expect when running the script:
<img width="1251" height="915" alt="image" src="https://github.com/user-attachments/assets/325b81e2-8745-45dc-89e1-92ddb7791797" />
<img width="1251" height="915" alt="image" src="https://github.com/user-attachments/assets/ef709b00-0cce-489a-9d2c-1582167f68d4" />

