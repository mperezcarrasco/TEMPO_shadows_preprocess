import glob
import h5py
import numpy as np
import matplotlib.pyplot as plt

# Filename
file= 'L1/TEMPO_RAD_L1_V04_20250909T180538Z_S009G01-034.nc'
files = glob.glob('L1/*.nc')
print(files)
for file in files:
    # Read the red, green, and blue variables
    with h5py.File(file, 'r') as f:
        red   = f['cloud_mask_group']['red'][:]
        green = f['cloud_mask_group']['green'][:]
        blue  = f['cloud_mask_group']['blue'][:]
        cloud  = f['cloud_mask_group']['cloud_mask'][:]
    # Clip the values exceeding 1.0.
    # (The Python library I use here allows scales of 0-255 int or 0-1 float.)
    red   = np.where((red   > 1.0), 1.0, red)[:,:,np.newaxis]
    green = np.where((green > 1.0), 1.0, green)[:,:,np.newaxis]
    blue  = np.where((blue  > 1.0), 1.0, blue)[:,:,np.newaxis]

    # Apply the power of 0.4 to make the land look brighter.
    # (Without this treatment, the images look pretty dark.)
    red   = red**0.4
    green = green**0.4
    blue  = blue**0.4

    # Construct the RGB variable.
    rgb = np.concatenate((red, green, blue), axis=2)
    # Transpose the array so that the North-South dimension is placed on the y-axis of the image.
    rgb = np.transpose(rgb, (1,0,2))
    # Flip the array so that the North is placed on the upper side of the image.
    rgb = np.flip(rgb, axis=0)
    # !!! Note: Lines 26-31 are not needed when you use latitudes and longitudes. !!!

    cloud = np.transpose(cloud, (1,0))
    cloud = np.flip(cloud, axis=0)

    # Plot the figure.
    fig, ax = plt.subplots(1,2, figsize=(10, 6))
    ax[0].pcolormesh(rgb)
    ax[1].pcolormesh(cloud)
    fig.tight_layout()

    for a in ax:
        a.axis('off')
    # Save the figure.
    fig.savefig(f'plots/rgb_{file.split('/')[-1]}.png')
    plt.close()