# detector.py

import fastdeploy as fd
import cv2
import os
import numpy as np

class FaceDetector:
    def __init__(self, det_model_file="./models/scrfd_500m_bnkps_shape640x640_rk3588_unquantized.rknn", 
                       reid_model_file="./models/ms1mv3_arcface_r18_rk3588_unquantized.rknn", 
                       database_path="./images"):
        # Initialize model paths and database path
        self.det_model_file = det_model_file
        self.reid_model_file = reid_model_file
        self.database_path = database_path
        
        # Initialize models
        self.det_model, self.reid_model = self.initialize_models()

        # Load the database
        self.database = self.update_database()

    def initialize_models(self):
        """
        Initializes the face detection and re-identification models.
        """
        det_runtime_option = fd.RuntimeOption()
        det_runtime_option.use_rknpu2()
        det_runtime_option.disable_paddle_log_info()

        reid_runtime_option = fd.RuntimeOption()
        reid_runtime_option.use_rknpu2()
        reid_runtime_option.disable_paddle_log_info()

        det_model = fd.vision.facedet.SCRFD(
            self.det_model_file, runtime_option=det_runtime_option, model_format=fd.ModelFormat.RKNN
        )
        det_model.disable_normalize()
        det_model.disable_permute()

        reid_model = fd.vision.faceid.ArcFace(
            self.reid_model_file, runtime_option=reid_runtime_option, model_format=fd.ModelFormat.RKNN
        )
        reid_model.preprocessor.disable_normalize()
        reid_model.preprocessor.disable_permute()

        return det_model, reid_model

    def update_database(self):
        """
        Loads all images from the database path and returns their embeddings.
        """
        embeddings = {}
        for filename in os.listdir(self.database_path):
            if filename.endswith(".png"):
                image_path = os.path.join(self.database_path, filename)
                image = cv2.imread(image_path)
                embeddings[filename.split(".")[0]] = self.reid_model.predict(image).embedding
        return embeddings

    def align_face_5points(self, image, landmarks, output_size=(112, 112)):
        """
        Aligns a face in an image based on the detection of 5 points model coordinates.
        """
        desired_left_eye = (0.35, 0.35)
        desired_face_width, desired_face_height = output_size

        eyes_center = (
            (landmarks[0][0] + landmarks[1][0]) // 2,
            (landmarks[0][1] + landmarks[1][1]) // 2,
        )
        dy = landmarks[1][1] - landmarks[0][1]
        dx = landmarks[1][0] - landmarks[0][0]
        angle = np.degrees(np.arctan2(dy, dx))

        desired_right_eye_x = 1.0 - desired_left_eye[0]
        dist = np.sqrt((dx**2) + (dy**2))
        desired_dist = desired_right_eye_x - desired_left_eye[0]
        desired_dist *= desired_face_width
        scale = desired_dist / dist

        M = cv2.getRotationMatrix2D(eyes_center, angle, scale)
        tX = desired_face_width * 0.5
        tY = desired_face_height * desired_left_eye[1]
        M[0, 2] += tX - eyes_center[0]
        M[1, 2] += tY - eyes_center[1]

        output = cv2.warpAffine(
            image, M, (desired_face_width, desired_face_height), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )

        return output

    def cosine_similarity(self, a, b):
        """
        Computes cosine similarity between two vectors.
        """
        a = np.array(a)
        b = np.array(b)
        return np.dot(a, b) / (np.linalg.norm(a, ord=2) * np.linalg.norm(b, ord=2))

    def compare_embeddings_and_find_top(self, embedding, embeddings_dict):
        """
        Compares the given embedding with the database and returns the top match.
        """
        similarities = {}
        if len(embeddings_dict.keys()) == 0:
            return "", 0

        for name, target_embedding in embeddings_dict.items():
            similarity = self.cosine_similarity(embedding, target_embedding)
            similarities[name] = similarity

        top_name = max(similarities, key=similarities.get)
        top_similarity = similarities[top_name]

        return top_name, top_similarity

    def detect_faces_in_image(self, image, sim_threshold=0.5):
        """
        Detect faces in the given image and return a list of tuples with name and coordinates.
        """
    
        face_detection_result = self.det_model.predict(image, conf_threshold=0.5)
        face_detection_result.scores = list(map(lambda x: 1.0 if x == 0.5 else x, face_detection_result.scores))
        landmarks_by_face = [face_detection_result.landmarks[i:i + 5] for i in range(0, len(face_detection_result.landmarks), 5)]
        faces = [self.align_face_5points(image, landmark) for landmark in landmarks_by_face]

        detected_faces = []
        for face, box in zip(faces, face_detection_result.boxes):
            reid_result = self.reid_model.predict(face)
            name, similarity = self.compare_embeddings_and_find_top(reid_result.embedding, self.database)

            # Calculate the center of the bounding box
            center_x = (box[0] + box[2]) / 2
            center_y = (box[1] + box[3]) / 2
            center = (int(center_x), int(center_y))

            if similarity >= sim_threshold:
                detected_faces.append((name, box, center))
            else:
                detected_faces.append(("Unknown", box, center))

        return detected_faces

    def draw_bounding_boxes(self, image, detections, output_path=None):
        """
        Draw bounding boxes around the detected faces and save or return the image.
        """

        for name, box, center in detections:
            box = list(map(int, box))  # Ensure the coordinates are integers
            if name == "Unknown":
                color = (0, 0, 255)  # Red for unknown faces
            else:
                color = (0, 255, 0)  # Green for known faces
            cv2.rectangle(image, (box[0], box[1]), (box[2], box[3]), color, 2)

            # Draw center point
            cv2.circle(image, (center[0], center[1]), 5, (255, 0, 0), -1)  # Blue center point
            cv2.putText(
                image, name, (box[0], box[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2
            )
        #if output_path:
        #    cv2.imwrite(output_path, image)
        return image



