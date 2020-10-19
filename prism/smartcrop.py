import numpy as np
import cv2
import sys
import os
import numpy as np

def get_cv_image(img_path):
    assert os.path.exists(img_path)
    img = cv2.imread(img_path)
    return img

def rescale_and_convert_to_bw(img, size_w_or_h=500):
    h, w, channels = img.shape
    wh = size_w_or_h
    aspect = h/float(w)
    nh = int(wh * aspect)
    mimg = cv2.resize(img, (size_w_or_h, nh))
    print("converting to nh", size_w_or_h, nh)
    gray = cv2.cvtColor(mimg, cv2.COLOR_BGR2GRAY)
    # cv2.equalizeHist(gray, gray)
    return gray

def has_faces(gray):
    instpath = '/home/vagrant/opencv/data/haarcascades'

    if os.path.exists('/usr/share/opencv/haarcascades'):
        instpath = '/usr/share/opencv/haarcascades'

    p = '%s/haarcascade_frontalface_default.xml' % instpath

    face_cascade = cv2.CascadeClassifier(p)
    eye_cascade = cv2.CascadeClassifier('%s/haarcascade_eye.xml' % instpath)
    faces = face_cascade.detectMultiScale(gray, 1.2, 3)
    # TODO: maybe we should try with different cascades here
    print("found faces ???", faces)
    if len(faces) > 0:
        # TODO: which face is bigger ? more important
        for face in faces:
            x,y,w,h = face
            return int(x + w/2), int(y + h/2)
    return False

    # for (x,y,w,h) in faces:
    #     cv2.rectangle(img,(x,y),(x+w,y+h),(255,0,0),2)
    #     roi_gray = gray[y:y+h, x:x+w]
    #     roi_color = img[y:y+h, x:x+w]
    #     eyes = eye_cascade.detectMultiScale(roi_gray)
    #     for (ex,ey,ew,eh) in eyes:
    #         cv2.rectangle(roi_color,(ex,ey),(ex+ew,ey+eh),(0,255,0),2)

def has_corners(gray):
    corners = cv2.goodFeaturesToTrack(gray, 8, 0.04, 0.5, useHarrisDetector=False)
    corners = np.int0(corners)
    ret = []
    for i in corners:
        ret.append(i.ravel()) # (x, y)
    return ret

def find_biggest_sift_feature(gray):
    surf_params = {"_hessianThreshold":1000,
     "_nOctaves":4,
    "_nOctaveLayers":2,
    "_extended":1,
    "_upright":0}

    # cv2.xfeatures2d.SURF_create()
    # surf = cv2.SURF(400)

    # surf = cv2.SURF(**surf_params)
    # d = "SIFT"
    d = "SURF"
    surf_detector = cv2.FeatureDetector_create(d)
    surf_descriptor = cv2.DescriptorExtractor_create(d)
    surfDescriptorExtractor = cv2.DescriptorExtractor_create(d)

    keypoints = surf_detector.detect(gray, None) #, mask=None, useProvidedKeypoints=False)
    (keypoints, descriptors) = surfDescriptorExtractor.compute(gray, keypoints)

    keypoints = sorted(keypoints, key=lambda k: k.size, reverse=True)

    ret = []
    for kp in keypoints[0:8]:
        x = int(kp.pt[0])
        y = int(kp.pt[1])
        size = int(kp.size)
        ret.append((x,y, size))
    return ret

def in_circle(center_x, center_y, radius, x, y):
    square_dist = (center_x - x) ** 2 + (center_y - y) ** 2
    return square_dist <= radius ** 2

def which_keypoint(keypoints, corners):
    """
        returns the keypoint that has max. corners
    """
    l = []
    for kp in keypoints:
        x, y, size = kp
        cnt = 0
        for corner in corners:
            c_x, c_y = corner
            if in_circle(x, y, size, c_x, c_y):
                cnt += 1
        print(">> size >>", x, y, size, cnt, cnt / float(size))
        l.append((kp, cnt / float(size) ))
    return sorted(l, key=lambda l: l[1])[-1][0]

def point_of_interest(filepath):
    print("file path", filepath)
    img = get_cv_image(filepath)
    gray = rescale_and_convert_to_bw(img, 500)
    face_location = has_faces(gray)
    x, y = None, None
    debug = False

    if not face_location:
        corners = has_corners(gray)
        keypoints = find_biggest_sift_feature(gray)
        kp = which_keypoint(keypoints, corners)
        x, y, size = kp

        # if debug:
        #     for i in corners:
        #         cv2.circle(gray,(i[0], i[1]), 5, 255, -1)
        #         cv2.circle(gray, (x, y), size, (0, 128, 0))
        #         cv2.imwrite('/prism/test_images/output.png', gray)

    else:
        x, y = face_location

    print("found kp at", x, y)
    print("original shape", img.shape)
    # TODO: calc x, y from 300 pix
    org_h, org_w, channels = img.shape
    print(">>> gray shape", gray.shape)
    h, w = gray.shape
    x = int(x * (float(org_w) / w))
    y = int(y * (float(org_h) / h))
    print("x, y", x, y)

    if debug:
        if not face_location:
            cv2.circle(img, (x, y), int(size * (float(org_w) / w)), (0, 128, 0))
            cv2.imwrite('/prism/test_images/output-2.png', img)
        else:
            cv2.rectangle(img,(x-50,y-50),(x+ 50, y+ 50),(255,0,0),2)
            cv2.imwrite('/prism/test_images/output-2.png', img)

    return x, y


if __name__ == '__main__':
    img = get_cv_image(sys.argv[1])
    gray = rescale_and_convert_to_bw(img, 500)
    faces = has_faces(gray)
    if not faces:
        gray = rescale_and_convert_to_bw(img, 200)
        corners = has_corners(gray)
        for i in corners:
            cv2.circle(gray, (i[0], i[1]), 5, 255, -1)

        keypoints = find_biggest_sift_feature(gray)
        # for kp in keypoints:
        #     x, y, size = kp
        #     print ">>>", size
        #     cv2.circle(img, (x, y), size, (0, 128, 0))

        kp = which_keypoint(keypoints, corners)

        x, y, size = kp
        print(">>>", size)
        cv2.circle(gray, (x, y), size, (0, 128, 0))
    else:
        x, y = faces
        cv2.rectangle(gray, (x-50,y-50),(x+ 50, y+ 50),(255,0,0),2)

    cv2.imwrite('%s-output.png' % sys.argv[1], gray)
