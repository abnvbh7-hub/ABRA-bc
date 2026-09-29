import cv2
import numpy as np
from insightface.app import FaceAnalysis

app = FaceAnalysis(
    name="buffalo_l",
    providers=["CPUExecutionProvider"]
)

app.prepare(ctx_id=-1, det_size=(640, 640))


def get_embedding(image_path):
    image = cv2.imread(image_path)

    if image is None:
        raise FileNotFoundError(f"Cannot load {image_path}")

    faces = app.get(image)

    if len(faces) == 0:
        return None

    # Use the largest detected face
    face = max(
        faces,
        key=lambda f: (f.bbox[2] - f.bbox[0]) *
                      (f.bbox[3] - f.bbox[1])
    )

    embedding = face.embedding.astype(np.float32)

    # Normalize embedding
    embedding /= np.linalg.norm(embedding)

    return embedding


def compare_faces(img1, img2):
    emb1 = get_embedding(img1)
    emb2 = get_embedding(img2)

    if emb1 is None or emb2 is None:
        return None

    return float(np.dot(emb1, emb2))


similarity = compare_faces("test2.jpg", "test3.jpg")

if similarity is not None:
    print(f"Similarity: {similarity:.4f}")
else:
    print("No face detected.")