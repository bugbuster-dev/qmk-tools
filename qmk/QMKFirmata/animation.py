# import necessary libraries in RGBAnimationTab.py

#-------------------------------------------------------------------------------
# matplotlib animation examples
# return the "init" and "animate" methods to be used with "matplotlib animation"
# in animate_methods() here below
#
# self.figure, self.ax are already defined
#-------------------------------------------------------------------------------

# return the init, animate methods pair
def animate_methods(self):
    methods = "init_wave","animate_wave"
    #methods = "init_rect","animate_rect"
    #methods = "init_random_colors","animate_random_colors"
    #methods = "init_spiral","animate_spiral"
    #methods = "init_audio_anim","animate_audio"
    #methods = "init_circle_wave","animate_circle_wave"
    return methods

#-------------------------------------------------------------------------------
# self.figure, self.ax are already defined
def init_random_colors(self):
    rows, cols = 6, 17  # Grid size
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
    rows, cols = 6, 17  # Grid size
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
    self.ax.set_xlim(-5, 5)
    self.ax.set_ylim(-1, 1)

    self.figure.set_facecolor('black')
    # Line object for the standing wave
    self.standing_wave_line = self.ax.plot([], [], color='red', lw=40)
    self.standing_wave_line[0].set_data([], [])

    return self.standing_wave_line

def animate_wave(self, i):
    #print("animate_wave")
    x_max = 20
    n_waves = 3
    x = np.linspace(0, x_max, 100)

    amplitude = np.sin(np.pi * i / self.n_frames) * 1.1
    y = amplitude * np.sin(n_waves * 2 * np.pi * (x - x_max / 2) / x_max) * np.cos(2 * np.pi * i / 50)
    self.standing_wave_line[0].set_data((x - x_max / 2), y)

    return self.standing_wave_line

#-------------------------------------------------------------------------------
def init_circle_wave(self):
    self.ax.set_xlim(0, 2)
    self.ax.set_ylim(0, 2)
    #self.ax.set_aspect('equal', adjustable='box')
    self.waves = []

def animate_circle_wave(self, i):
    #print("animate_raindrops")
    def random_color():
        return (random.random(), random.random(), random.random())

    self.ax.clear()
    # new wave every N frames
    if i % 20 == 0:
        x, y = random.uniform(0.5, 1.5), random.uniform(0.5, 1.5)
        wave_color = random_color()
        self.waves.append((x, y, 0, wave_color))

    # update the radius
    new_waves = []
    for x, y, r, color in self.waves:
        if r < 1.2:
            alpha = 1 - r/1.2
            circle = plt.Circle((x, y), r, color=color, fill=False, linewidth=100, alpha=alpha)
            self.ax.add_patch(circle)
            new_waves.append((x, y, r + 0.05, color))
    self.waves[:] = new_waves
    return []

#-------------------------------------------------------------------------------
def init_rect(self):
    self.figure.set_facecolor('black')

    self.rect = plt.Rectangle((0.5, 0.5), 0.15, 0.3, color="blue")
    self.ax.add_patch(self.rect)
    self.ax.set_xlim(0, 1)
    self.ax.set_ylim(0, 1)

    # velocity and direction
    self.velocity = np.array([0.01, 0.007])
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
def init_audio_anim(self):
    self.N_PEAKS = 31
    self.ax.set_xlim(0, self.N_PEAKS - 1)
    self.ax.set_ylim(0, 200)

    self.x = np.arange(self.N_PEAKS)
    self.spectrum, = self.ax.plot([], [], color='skyblue', lw=20)
    self.spectrum.set_data(self.x, np.zeros(self.N_PEAKS))
    #print("init_audio")
    return self.spectrum,

def animate_audio(self, i):
    #print("animate_audio")
    peak_levels = self.audio_peak_levels()
    if peak_levels:
        #print(peak_levels)
        self.spectrum.set_ydata(peak_levels)
    return self.spectrum,

