import sys
import os
import pymongo

sys.path.insert(0, r'd:\Gradautaion_Project\Integrated_App')
from app import db

# 1. Remove non-Egyptian or duplicate junk
db.locations.delete_many({'name': {'$in': ['Süleymaniye Mosque', 'S\u00fcleymaniye Mosque', 'car', 'keyboard', 'Unknown', 'Eiffel Tower']}})
db.objects.delete_many({'name': {'$in': ['Süleymaniye Mosque', 'S\u00fcleymaniye Mosque', 'car', 'keyboard', 'Unknown', 'Eiffel Tower']}})

# 2. Enrich Tahrir Square
db.locations.update_one({'location_id': 'L_5D8634'}, {'$set': {
    'name': 'Tahrir Square & Downtown',
    'name_ar': 'ميدان التحرير ووسط البلد',
    'category': 'landmarks',
    'tag_ar': 'قلب القاهرة وتراثها المعماري',
    'tag_en': 'Heart of Historic Cairo',
    'description_ar': 'ميدان التحرير العريق والمتحف المصري ومباني وسط البلد ذات الطابع المعماري الأوروبي الكلاسيكي.',
    'image_url': '/static/images/image14.jpeg'
}})

db.objects.update_one({'object_id': 'O_5D8634'}, {'$set': {
    'name': 'Tahrir Square Monument',
    'name_ar': 'مسلة ميدان التحرير',
    'class_name': 'Tahrir-Square',
    'location_id': 'L_5D8634',
    'category': 'landmarks',
    'image_url': '/static/images/image14.jpeg',
    'description_ar': 'المسلة الفرعونية التي تتوسط ميدان التحرير محاطة بالكباش الأثرية ونافورة العاصمة.'
}})

# 3. Add Karnak Hypostyle Hall
db.objects.update_one({'object_id': 'O007'}, {'$set': {
    'object_id': 'O007',
    'name': 'Karnak Hypostyle Hall',
    'name_ar': 'بهو الأساطين بمعبد الكرنك',
    'class_name': 'Karnak-Temple',
    'location_id': 'L004',
    'category': 'landmarks',
    'image_url': '/static/images/image18.jpeg',
    'description_ar': 'أعظم قاعة أعمدة في العالم القديم تضم 134 عموداً حجرياً ضخماً بنقوش هيروغليفية تخلد أمجاد الفراعنة.',
    'latitude': 25.7188,
    'longitude': 32.6573
}}, upsert=True)

print('MongoDB Atlas records curated successfully!')
