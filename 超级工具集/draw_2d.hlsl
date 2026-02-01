// **** RESPONSIVE UI SHADER WITH ASPECT CORRECTED ROTATION ****
// Updated for v30.1
// Contributors: SinsOfSeven

Texture1D<float4> IniParams : register(t120);

// x87, y87 = Width, Height (0..1 screen space)
// z87, w87 = Top-Left X, Top-Left Y (0..1 screen space)
// x86      = Rotation in Radians
// y86      = Aspect Ratio (Width / Height), e.g., 1.777

#define SIZE IniParams[87].xy
#define TL_POS IniParams[87].zw
#define ROTATION IniParams[86].x
#define ASPECT IniParams[86].y

struct vs2ps {
    float4 pos : SV_Position0;
    float2 uv : TEXCOORD1;
};

#ifdef VERTEX_SHADER
void main(
        out vs2ps output,
        uint vertex : SV_VertexID)
{
    // 1. Calculate Center of the element
    float2 centerUV = TL_POS.xy + SIZE.xy * 0.5;
    
    // 2. Determine local vertex offset relative to center (unrotated)
    float2 hSize = SIZE.xy * 0.5;
    float2 localPos;
    float2 uv;

    switch(vertex) {
        case 0: // Top Right
            localPos = float2(hSize.x, -hSize.y); 
            uv = float2(1, 0);
            break;
        case 1: // Bottom Right
            localPos = float2(hSize.x, hSize.y);
            uv = float2(1, 1);
            break;
        case 2: // Top Left
            localPos = float2(-hSize.x, -hSize.y);
            uv = float2(0, 0);
            break;
        case 3: // Bottom Left
            localPos = float2(-hSize.x, hSize.y);
            uv = float2(0, 1);
            break;
        default:
            localPos = float2(0,0);
            uv = float2(0,0);
            break;
    };

    // 3. Apply Aspect Ratio Correction BEFORE Rotation
    // We treat Y as the baseline. We scale X by Aspect Ratio to make coordinates "square" in pixel space.
    localPos.x *= ASPECT;

    // 4. Apply Rotation
    float c = cos(ROTATION);
    float s = sin(ROTATION);
    
    float2 rotatedPos;
    rotatedPos.x = localPos.x * c - localPos.y * s;
    rotatedPos.y = localPos.x * s + localPos.y * c;
    
    // 5. Restore Aspect Ratio (Convert back to 0..1 UV space)
    rotatedPos.x /= ASPECT;
    
    // 6. Translate back to Center
    float2 finalUV = centerUV + rotatedPos;
    
    // 7. Convert UV to Clip Space
    output.pos.x = finalUV.x * 2.0 - 1.0;
    output.pos.y = (1.0 - finalUV.y) * 2.0 - 1.0;
    output.pos.zw = float2(0, 1);
    
    output.uv = uv;
}
#endif

#ifdef PIXEL_SHADER
Texture2D<float4> tex : register(t100);

void main(vs2ps input, out float4 result : SV_Target0)
{
    float2 dims;
    tex.GetDimensions(dims.x, dims.y);
    if (!dims.x || !dims.y) discard;
    
    float2 sampleUV = input.uv;
    sampleUV.y = 1 - sampleUV.y; 
    
    result = tex.Load(int3(sampleUV.xy*dims.xy, 0));
}
#endif