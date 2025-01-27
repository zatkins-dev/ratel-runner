SetFactory("OpenCASCADE");
DefineConstant[
  cl = {60, Min 0.00001, Max 1000, Step 0.01, Name "Parameters/Target Characteristic Length"},
  element_order = {1, Min 1, Max 3, Step 1, Name "Parameters/Element order"},
  height_scale = {1, Min 0, Max 2, Step 0.1, Name "Parameters/Height scale"},
];


radius = 2.5342;
height = 4.4203 * height_scale;
layers = Ceil(height / cl);
Disk(1) = {0, 0, 0, radius};
Recombine Surface {1};
Extrude {0, 0, height} { Surface{1}; Layers{layers}; Recombine; }

Coherence;

Physical Surface("bottom",1) = {1};
Physical Surface("top",2) = {3};
Physical Surface("outside",3) = {2};
Physical Volume("puck", 1) = {1};

Mesh.MeshSizeMax = 1;
Mesh.MeshSizeMin = 0.5;
Mesh.MeshSizeFactor = cl;
Mesh.ElementOrder = element_order;
Mesh.HighOrderOptimize = element_order;
