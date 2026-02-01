// --- START OF FILE 形态anim.hlsl ---

// **** ADDITIVE ANIMATION SHADER - PER-NAME INTENSITY (MULTI-SLOT BLENDING) ****
// Contributors: Zlevir, Assistant
// Version: 3.3 (Stable Blending - Pure Linear Interpolation)

// --- DEFINES ---
#define MAX_SLOTS 24 // Maximum number of shape key slots to blend simultaneously (t51 to t58)

struct VertexAttributes {
    float3 position;
    float3 normal;
    float4 tangent;
};

// --- I/O BUFFERS ---
RWStructuredBuffer<VertexAttributes> rw_buffer : register(u5);
StructuredBuffer<VertexAttributes> base : register(t50);
StructuredBuffer<VertexAttributes> shapekeys[MAX_SLOTS] : register(t51);

// --- PARAMETERS ---
Texture1D<float4> IniParams : register(t120);

// --- [PYTHON-MANAGED BLOCK START] ---
// The Blender plugin will dynamically generate all necessary #define statements
// for intensities (FREQ) and vertex ranges (START/END) here.
// This block is intentionally left empty in the template.
// --- [PYTHON-MANAGED BLOCK END] ---


[numthreads(16, 1, 1)]
void main(uint3 threadID : SV_DispatchThreadID)
{
    uint i = threadID.x;
    
    // Start with the base mesh attributes
    VertexAttributes output = rw_buffer[i];
    
    // Initialize total difference vectors.
    float3 total_diff_position = float3(0.0, 0.0, 0.0);
    float3 total_diff_normal = float3(0.0, 0.0, 0.0);
    float3 total_diff_tangent = float3(0.0, 0.0, 0.0); // Tangent diff is float3, we ignore w

    // --- [PYTHON-MANAGED LOGIC START] ---
    // The Blender plugin will dynamically generate the blending logic for each
    // shape key slot based on the classification text.
    // This block is intentionally left empty in the template.
    // --- [PYTHON-MANAGED LOGIC END] ---

    // [CRITICAL FIX] Apply the final accumulated differences using pure linear addition,
    // exactly like the old working shader. DO NOT normalize here.
    output.position += total_diff_position;
    output.normal += total_diff_normal;
    output.tangent.xyz += total_diff_tangent;
    // The 'w' component of the tangent remains unchanged from the base mesh.
    
    rw_buffer[i] = output;
}

// --- END OF FILE 形态anim.hlsl ---