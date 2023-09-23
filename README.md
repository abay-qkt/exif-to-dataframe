# exif-to-dataframe
load exif from photos and make dataframe

usage example
```python
from exif_to_dataframe import get_exif_df
root_path = Path("path/to/photo_directory") # select photo folder
path_list = list(root_path.glob("**/*.JPG")) # get jpeg path list
exif_df = get_exif_df(path_list) # get exif dataframe
```


for more detail<br>
https://note.com/abay_ksg/m/m2c4d5ecd9d83