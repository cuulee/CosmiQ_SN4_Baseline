import keras
import cv2
import numpy as np
import os


class DataGenerator(keras.utils.Sequence):
    """Data generator to produce matching image-mask pairs from the generator array."""
    def __init__(self, image_arr, mask_arr, batch_size=32, crop=False,
                 output_x=256, output_y=256, shuffle=True, flip_x=False,
                 zoom_range=None, flip_y=False, rotate=False,
                 rescale_brightness=None, output_dir=''):
        self.images = image_arr
        self.masks = mask_arr
        self.batch_size = batch_size
        self.initial_width = image_arr.shape[2]
        self.initial_height = image_arr.shape[1]
        self.output_x = output_x
        self.output_y = output_y
        self.crop = crop
        self.shuffle = shuffle
        self.flip_x = flip_x
        self.flip_y = flip_y
        self.rotate = rotate
        self.zoom_range = zoom_range
        self.output_dir = output_dir
        self.output_ctr = 0
        self.rescale_brightness = rescale_brightness
        self.on_epoch_end()

    def on_epoch_end(self):
        'Update indices, rotations, etc. after each epoch'
        # select one collect per image
        self.collect_indexes = np.random.choice(
            np.arange(self.images.shape[0]),
            size=self.images.shape[1])
        if self.shuffle:
            np.random.shuffle(self.collect_indexes)
        # reorder images
        self.image_indexes = np.arange(self.images.shape[1])
        if self.shuffle:
            np.random.shuffle(self.image_indexes)
        if self.crop:
            self.x_mins = np.random.randint(
                0, self.images.shape[3]-self.output_x, size=self.batch_size
            )
            self.y_mins = np.random.randint(
                0, self.images.shape[2] - self.output_y, size=self.batch_size
            )
        if self.flip_x:
            self.x_flips = np.random.choice(
                [False, True], size=self.batch_size
            )
        if self.flip_y:
            self.y_flips = np.random.choice(
                [False, True], size=self.batch_size
            )
        if self.rotate:
            self.n_rotations = np.random.choice(
                [0, 1, 2, 3], size=self.batch_size
            )
        if self.rescale_brightness is not None:
            self.amt_to_scale = np.random.uniform(
                low=self.rescale_brightness[0],
                high=self.rescale_brightness[1],
                size=self.batch_size
            )
        if self.zoom_range is not None:
            if (1-self.zoom_range)*self.images.shape[2] < self.output_y:
                self.zoom_range = self.output_y/self.images.shape[2]
            if (1-self.zoom_range)*self.images.shape[3] < self.output_x:
                self.zoom_range = self.output_x/self.images.shape[3]
            self.zoom_amt_y = np.random.uniform(
                low=1-self.zoom_range,
                high=1+self.zoom_range,
                size=self.batch_size
            )
            self.zoom_amt_x = np.random.uniform(
                low=1-self.zoom_range,
                high=1+self.zoom_range,
                size=self.batch_size
            )

    def _data_generation(self, collect_idxs, image_idxs):
        # initialize
        X = np.empty((self.batch_size, self.output_y, self.output_x,
                      self.images.shape[4]))
        y = np.empty((self.batch_size, self.output_y, self.output_x,
                     self.masks.shape[3]))
        for i in range(self.batch_size):
            curr_im = self.images[collect_idxs[i],
                                  image_idxs[i],
                                  :, :, :]
            curr_mask = self.masks[image_idxs[i], :, :, :]
            if self.zoom_range is not None:
                curr_im = cv2.resize(
                    curr_im,
                    (int(curr_im.shape[1]*self.zoom_amt_x[i]),
                     int(curr_im.shape[0]*self.zoom_amt_y[i])))
                curr_mask = cv2.resize(
                    curr_mask.astype('uint8'),
                    (int(curr_mask.shape[1]*self.zoom_amt_x[i]),
                     int(curr_mask.shape[0]*self.zoom_amt_y[i])))
                if len(curr_mask.shape) < 3:  # add third axis if absent
                    curr_mask = curr_mask[:, :, np.newaxis]
                curr_mask = curr_mask > 0
                pad_amt = [0, 0]
                if self.zoom_amt_y[i] < 1:
                    pad_amt[0] = int(self.images.shape[2]*self.zoom_amt_y[i]*0.5)
                if self.zoom_amt_x[i] < 1:
                    pad_amt[1] = int(self.images.shape[3]*self.zoom_amt_x[i]*0.5)
                if pad_amt != [0, 0]:
                    curr_mask = np.pad(
                        curr_mask,
                        pad_width=((pad_amt[0], pad_amt[0]),
                                   (pad_amt[1], pad_amt[1]),
                                   (0, 0)),
                        mode='reflect')
                    curr_im = np.pad(
                        curr_im,
                        pad_width=((pad_amt[0], pad_amt[0]),
                                   (pad_amt[1], pad_amt[1]),
                                   (0, 0)),
                        mode='reflect')
            if self.crop:
                curr_im = curr_im[self.y_mins[i]:self.y_mins[i]+self.output_y,
                                  self.x_mins[i]:self.x_mins[i]+self.output_x,
                                  :]
                curr_mask = curr_mask[
                    self.y_mins[i]:self.y_mins[i]+self.output_y,
                    self.x_mins[i]:self.x_mins[i]+self.output_x,
                    :]
            else:
                curr_im = cv2.resize(curr_im, (self.output_y, self.output_x,
                                               self.images.shape[2]))
                curr_mask = cv2.resize(curr_im, (self.output_y, self.output_x,
                                                 self.masks.shape[2]))
            if self.flip_x:
                if self.x_flips[i]:
                    curr_im = np.flip(curr_im, axis=0)
                    curr_mask = np.flip(curr_mask, axis=0)
            if self.flip_y:
                if self.y_flips[i]:
                    curr_im = np.flip(curr_im, axis=1)
                    curr_mask = np.flip(curr_mask, axis=1)
            if self.rotate:
                to_go = 0
                while to_go < self.n_rotations[i]:
                    curr_im = np.rot90(curr_im)
                    curr_mask = np.rot90(curr_mask)
                    to_go += 1
            if self.rescale_brightness is not None:
                hsv = cv2.cvtColor(curr_im, cv2.COLOR_BGR2HSV)
                v = hsv[:, :, 2]*self.amt_to_scale[i]
                v = np.clip(v, 0, 255).astype('uint8')
                hsv[:, :, 2] = v
                curr_im = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
            X[i, :, :, :] = curr_im
            y[i, :, :, :] = curr_mask
        X = X/255.
        return X, y

    def __len__(self):
        'Denotes the number of batches per epoch'
        return int(np.floor(self.images.shape[1]/self.batch_size))

    def __getitem__(self, index):
        'Generate one batch of data'
        # Generate indexes of the batch
        col_inds = self.collect_indexes[index*self.batch_size:(index+1)*self.batch_size]
        im_inds = self.image_indexes[index*self.batch_size:(index+1)*self.batch_size]

        # Generate data
        X, y = self._data_generation(collect_idxs=col_inds, image_idxs=im_inds)
        if self.output_dir:
            np.save(os.path.join(
                self.output_dir, 'images_{}.npy'.format(self.output_ctr)),
                    X)
            np.save(os.path.join(
                self.output_dir, 'masks_{}.npy'.format(self.output_ctr)),
                    y)
            self.output_ctr += 1
        return X, y
