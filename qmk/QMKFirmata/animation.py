#-------------------------------------------------------------------------------
# the "init", "animate" methods to be used with "matplotlib animation"
def animate_methods(self):
    methods = "init_heart","animate_heart"
    #methods = "init_wave","animate_wave"
    #methods = "init_rect","animate_rect"
    #methods = "init_random_colors","animate_random_colors"
    methods = "init_spiral","animate_spiral"
    return methods

#-------------------------------------------------------------------------------

def init_random_colors(self):
    rows, cols = 6, 19  # Grid size
    rect_width, rect_height = 6, 1  # Rectangle dimensions
    xlim, ylim = cols * rect_width, rows * rect_height  # Plot area limits, accommodating all rectangles

    self.ax.set_xlim(0, xlim)
    self.ax.set_ylim(0, ylim)

    # Initialize rectangles in a grid without spacing
    rectangles = []
    for row in range(rows):
        for col in range(cols):
            x = col * rect_width
            y = ylim - (row + 1) * rect_height  # Positioning from the top, no spacing
            rect = Rectangle((x, y), rect_width, rect_height, edgecolor='none', facecolor=np.random.rand(3,))
            self.ax.add_patch(rect)
            rectangles.append(rect)

    self.rectangles = rectangles

def animate_random_colors(self, i):
    # Only change the color of each rectangle
    for rect in self.rectangles:
        rect.set_facecolor(np.random.rand(3)) # random rgb color

    return self.rectangles

#-------------------------------------------------------------------------------

def init_spiral(self):
    rows, cols = 6, 19  # Grid size
    rect_width, rect_height = 6, 1  # Rectangle dimensions
    xlim, ylim = cols * rect_width, rows * rect_height  # Plot area limits, accommodating all rectangles

    self.ax.set_xlim(0, xlim)
    self.ax.set_ylim(0, ylim)
    self.rows = rows
    self.cols = cols

    # Initialize rectangles in a grid without spacing
    rectangles = []
    for row in range(rows):
        for col in range(cols):
            x = col * rect_width
            y = ylim - (row + 1) * rect_height  # Positioning from the top, no spacing
            rect = Rectangle((x, y), rect_width, rect_height, edgecolor='none', facecolor='black')
            self.ax.add_patch(rect)
            rectangles.append(rect)

    self.rectangles = rectangles

    self.angle = 0


def animate_spiral(self, i):
    for rect in self.rectangles:
        rect.set_facecolor('black')

    self.angle += 10 + ((i/10)%15) * 5  # Increase the angle for rotation

    image_size = (self.cols, self.rows)
    center = (image_size[0] // 2, image_size[1] // 2)
    radius = self.cols // 2
    spiral_width = 2  # Width of the spiral band

    # Draw the spiral
    for i in range(radius * spiral_width):
        theta = 0.1 * i + np.radians(self.angle)
        x = center[0] + (i / spiral_width) * np.cos(theta)
        y = center[1] + (i / spiral_width) * np.sin(theta)
        if 0 <= x < image_size[0] and 0 <= y < image_size[1]:
            self.rectangles[int(y) * self.cols + int(x)].set_facecolor('blue')

    return self.rectangles

#-------------------------------------------------------------------------------

def init_wave(self):
    self.ax.set_xlim(-0.05, 0.05)
    self.ax.set_ylim(-0.05, 0.05)

    self.figure.set_facecolor('black')
    # Line object for the standing wave
    self.standing_wave_line, = self.ax.plot([], [], color='red', lw=25)
    self.standing_wave_line.set_data([], [])

    self.frames = 1000
    return self.standing_wave_line,


def animate_wave(self, i):
    x = np.linspace(0, self.x_size, 1000)
    #x = np.linspace(0, 2 * np.pi, 1000)

    amplitude = np.sin(np.pi * i / self.frames) * 1
    y = amplitude * np.sin(2 * 2 * np.pi * 2 * (x - self.x_size / 2) / self.x_size) * np.cos(2 * np.pi * i / 50)
    self.standing_wave_line.set_data((x - self.x_size / 2)/100, y/30)

    return self.standing_wave_line,

#-------------------------------------------------------------------------------

def init_rect(self):
    self.figure.set_facecolor('black')

    self.rect = plt.Rectangle((0.5, 0.5), 0.15, 0.3, color="blue")
    self.ax.add_patch(self.rect)
    self.ax.set_xlim(0, 1)
    self.ax.set_ylim(0, 1)

    # Initialize velocity and direction
    self.velocity = np.array([0.01, 0.007])

    self.frames = 1000
    self.rect.set_xy((0.45, 0.45))
    return self.rect,

def animate_rect(self, i):
    pos = self.rect.get_xy()
    pos += self.velocity

    # Check for collision with the walls and reverse velocity if needed
    if pos[0] <= 0 or pos[0] + self.rect.get_width() >= 1:
        self.velocity[0] = -self.velocity[0]
    if pos[1] <= 0 or pos[1] + self.rect.get_height() >= 1:
        self.velocity[1] = -self.velocity[1]

    self.rect.set_xy(pos)
    return self.rect,

#-------------------------------------------------------------------------------

def init_heart(self):
    self.figure.set_facecolor('green')
    self.ax.set_xlim(0, 1)
    self.ax.set_ylim(0, 1)

    # Heart shape in a pixel grid (1s and 0s)
    heart_shape = np.array([
        [0, 0, 1, 1, 0, 0, 1, 1, 0, 0],
        [0, 1, 1, 1, 1, 1, 1, 1, 1, 0],
        [1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        [1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        [0, 1, 1, 1, 1, 1, 1, 1, 1, 0],
        [0, 0, 1, 1, 1, 1, 1, 1, 0, 0],
        [0, 0, 0, 1, 1, 1, 1, 0, 0, 0],
        [0, 0, 0, 0, 1, 1, 0, 0, 0, 0]
    ])

    # Calculate the initial position and size of each square
    self.square_size = 0.08
    square_size = self.square_size
    heart_position = [0.5 - square_size*heart_shape.shape[1]/2 + 0.15, 0.5 - square_size*heart_shape.shape[0]/2]
    self.squares = []

    self.scale_w = 0.4
    # Create the pixel art heart using squares
    for i in range(heart_shape.shape[0]):
        row = heart_shape[i, :]
        for j in range(heart_shape.shape[1]):
            if row[j] == 1:
                y = heart_position[1] + (heart_shape.shape[0]-1-i)*square_size
                square = Rectangle((heart_position[0] + j*square_size*self.scale_w, y),
                               square_size, square_size, color="red")
                self.ax.add_patch(square)
                self.squares.append(square)

    return self.squares

def animate_heart(self, frame):
    square_size = self.square_size
    scale_factor = 1 + (np.sin(frame * np.pi / 15)+1) * 0.3  # Beat effect
    for square in self.squares:
        square.set_width(square_size * scale_factor*self.scale_w)
        square.set_height(square_size * scale_factor)
    return self.squares
