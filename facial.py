import cv2
import numpy as np
import base64
from typing import List, Dict, Any, Optional, Tuple
from insightface.app import FaceAnalysis

# Initialize FaceAnalysis singleton with antelopev2 (Glint360K ResNet-100 ArcFace) for maximum accuracy
_app = None

def get_face_app():
    global _app
    if _app is None:
        try:
            print("[FaceService] Initializing FaceAnalysis with antelopev2 (Glint360K ResNet-100 ArcFace)...")
            _app = FaceAnalysis(
                name="antelopev2",
                allowed_modules=["detection", "recognition"],
                providers=["CPUExecutionProvider"]
            )
            _app.prepare(ctx_id=-1, det_size=(640, 640))
            print("[FaceService] Successfully loaded antelopev2 model.")
        except Exception as err:
            print(f"[FaceService] antelopev2 load failed ({err}), falling back to buffalo_l...")
            try:
                _app = FaceAnalysis(
                    name="buffalo_l",
                    allowed_modules=["detection", "recognition"],
                    providers=["CPUExecutionProvider"]
                )
                _app.prepare(ctx_id=-1, det_size=(640, 640))
                print("[FaceService] Loaded buffalo_l model.")
            except Exception as err2:
                print(f"[FaceService] buffalo_l load failed ({err2}), falling back to buffalo_s...")
                _app = FaceAnalysis(
                    name="buffalo_s",
                    allowed_modules=["detection", "recognition"],
                    providers=["CPUExecutionProvider"]
                )
                _app.prepare(ctx_id=-1, det_size=(640, 640))
    return _app


def decode_image_bytes(image_bytes: bytes) -> Optional[np.ndarray]:
    """Decodes raw image bytes into an OpenCV BGR numpy array."""
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        print(f"[FaceService] Error decoding image bytes: {e}")
        return None


def crop_face_avatar(image: np.ndarray, bbox: List[int], target_size: int = 160) -> str:
    """Crops a face from an image with padding and returns a base64 JPEG data URL."""
    try:
        h, w, _ = image.shape
        x1, y1, x2, y2 = [int(v) for v in bbox]
        
        # Add margin around face
        face_w = x2 - x1
        face_h = y2 - y1
        margin_x = int(face_w * 0.20)
        margin_y = int(face_h * 0.25)
        
        crop_x1 = max(0, x1 - margin_x)
        crop_y1 = max(0, y1 - margin_y)
        crop_x2 = min(w, x2 + margin_x)
        crop_y2 = min(h, y2 + margin_y)
        
        crop = image[crop_y1:crop_y2, crop_x1:crop_x2]
        if crop.size == 0:
            return ""
            
        # Resize to standard avatar size
        resized = cv2.resize(crop, (target_size, target_size), interpolation=cv2.INTER_AREA)
        _, buffer = cv2.imencode('.jpg', resized, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        b64 = base64.b64encode(buffer).decode('utf-8')
        return f"data:image/jpeg;base64,{b64}"
    except Exception as e:
        print(f"[FaceService] Error cropping face avatar: {e}")
        return ""


def filter_overlapping_faces(faces: List[Dict[str, Any]], iou_threshold: float = 0.35) -> List[Dict[str, Any]]:
    """Filters duplicate/overlapping detections of the same face in a single photo."""
    if len(faces) <= 1:
        return faces
    sorted_faces = sorted(faces, key=lambda f: f.get("det_score", 0), reverse=True)
    kept = []
    for f in sorted_faces:
        box_a = f["bbox"]
        is_dup = False
        for k in kept:
            box_b = k["bbox"]
            xA = max(box_a[0], box_b[0])
            yA = max(box_a[1], box_b[1])
            xB = min(box_a[2], box_b[2])
            yB = min(box_a[3], box_b[3])
            interArea = max(0, xB - xA) * max(0, yB - yA)
            boxAArea = max(1, (box_a[2] - box_a[0]) * (box_a[3] - box_a[1]))
            boxBArea = max(1, (box_b[2] - box_b[0]) * (box_b[3] - box_b[1]))
            iou = interArea / float(boxAArea + boxBArea - interArea)
            
            # Check embedding similarity between two face crops in same photo
            sim = cosine_similarity(f["embedding"], k["embedding"])
            if iou > iou_threshold or (iou > 0.15 and sim > 0.65) or sim > 0.82:
                is_dup = True
                break
        if not is_dup:
            kept.append(f)
    return kept


def extract_faces_from_image(image_input: Any) -> List[Dict[str, Any]]:
    """
    Detects all faces in an image and extracts:
    - bounding box [x1, y1, x2, y2]
    - 512-dim unit-normalized embedding (list of floats)
    - avatar_data (base64 image crop)
    - det_score (confidence float)
    """
    app = get_face_app()
    
    if isinstance(image_input, bytes):
        image = decode_image_bytes(image_input)
    elif isinstance(image_input, str):
        image = cv2.imread(image_input)
    elif isinstance(image_input, np.ndarray):
        image = image_input
    else:
        raise ValueError("Invalid image input type")
        
    if image is None or image.size == 0:
        return []

    # Downscale very large images to max 1920px (maintains high face detail without excessive memory)
    h, w = image.shape[:2]
    max_dim = 1920
    scale = 1.0
    if max(h, w) > max_dim:
        scale = max_dim / float(max(h, w))
        new_w, new_h = int(w * scale), int(h * scale)
        image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
        
    detected_faces = app.get(image)
    results = []
    
    for face in detected_faces:
        try:
            bbox = [int(x) for x in face.bbox.tolist()]
            raw_emb = face.embedding.astype(np.float32)
            norm = np.linalg.norm(raw_emb)
            if norm > 0:
                normalized_emb = (raw_emb / norm).tolist()
            else:
                normalized_emb = raw_emb.tolist()
                
            avatar_b64 = crop_face_avatar(image, bbox)
            det_score = float(face.det_score) if hasattr(face, 'det_score') else 0.95
            
            # Filter low confidence detections (0.45 provides great precision with antelopev2)
            if det_score < 0.45:
                continue
                
            results.append({
                "bbox": bbox,
                "embedding": normalized_emb,
                "avatar_data": avatar_b64,
                "det_score": det_score
            })
        except Exception as e:
            print(f"[FaceService] Error parsing detected face: {e}")
            
    # Filter duplicate detections in the same photo
    return filter_overlapping_faces(results)


def cosine_similarity(emb1: List[float], emb2: List[float]) -> float:
    """Computes cosine similarity between two unit-normalized embedding vectors."""
    try:
        v1 = np.array(emb1, dtype=np.float32)
        v2 = np.array(emb2, dtype=np.float32)
        dot = float(np.dot(v1, v2))
        return dot
    except Exception as e:
        print(f"[FaceService] Similarity calculation error: {e}")
        return 0.0


def find_matching_person(
    face_embedding: List[float],
    people_list: List[Dict[str, Any]],
    similarity_threshold: float = 0.42
) -> Tuple[Optional[str], float]:
    """
    Compares a face embedding against all existing people (checking up to stored embeddings per person).
    Returns (matched_person_id, max_similarity_score).
    If no match exceeds similarity_threshold, returns (None, max_similarity_score).
    """
    best_person_id = None
    best_similarity = -1.0
    
    for person in people_list:
        person_id = str(person.get("id"))
        stored_embeddings = person.get("embeddings") or []
        
        # Handle if embeddings is stored as list of lists
        for stored_emb in stored_embeddings:
            if not stored_emb:
                continue
            sim = cosine_similarity(face_embedding, stored_emb)
            if sim > best_similarity:
                best_similarity = sim
                if sim >= similarity_threshold:
                    best_person_id = person_id
                    
    return best_person_id, best_similarity


def classify_face_match(
    face_embedding: List[float],
    people_list: List[Dict[str, Any]],
    auto_threshold: float = 0.42,
    review_threshold: float = 0.32
) -> Tuple[str, Optional[str], float]:
    """
    Classifies a face embedding against existing people.
    Returns (status, person_id, best_similarity).
    status can be:
      - 'auto_match': similarity >= auto_threshold (default 0.50)
      - 'needs_review': review_threshold <= similarity < auto_threshold (~40% match)
      - 'new_person': similarity < review_threshold
    """
    best_person_id = None
    best_similarity = -1.0
    
    for person in people_list:
        person_id = str(person.get("id"))
        stored_embeddings = person.get("embeddings") or []
        
        for stored_emb in stored_embeddings:
            if not stored_emb:
                continue
            sim = cosine_similarity(face_embedding, stored_emb)
            if sim > best_similarity:
                best_similarity = sim
                best_person_id = person_id
                
    if best_similarity >= auto_threshold and best_person_id is not None:
        return "auto_match", best_person_id, best_similarity
    elif best_similarity >= review_threshold and best_person_id is not None:
        return "needs_review", best_person_id, best_similarity
    else:
        return "new_person", None, max(0.0, best_similarity)