// --- START OF FILE 形态anim_standard_delta_v3.hlsl ---

// **** ADDITIVE ANIMATION SHADER - POSITION-ONLY DELTA (HYBRID BUFFERS) ****
// Contributors: Zlevir, Assistant
// Version: 3.0 (Correct Hybrid Buffer Handling)
// Description: Reads position deltas (stride=12) and applies them to a full vertex buffer (stride=40).

#define MAX_SLOTS 24 

struct VertexAttributes {
    float3 position;
    float3 normal;
    float4 tangent;
};

// --- I/O BUFFERS ---
RWStructuredBuffer<VertexAttributes> rw_buffer : register(u5);
StructuredBuffer<float3> shapekey_pos_deltas[MAX_SLOTS] : register(t51);

// --- PARAMETERS ---
Texture1D<float4> IniParams : register(t120);

// --- [PYTHON-MANAGED BLOCK START] ---
// --- [PYTHON-MANAGED BLOCK END] ---

[numthreads(16, 1, 1)]
void main(uint3 threadID : SV_DispatchThreadID)
{
    uint i = threadID.x;
    
    // Start with the base mesh attributes (copied to rw_buffer beforehand)
    VertexAttributes output = rw_buffer[i];
    
    float3 total_diff_position = float3(0.0, 0.0, 0.0);

    // --- [PYTHON-MANAGED LOGIC START] ---
    // The Blender plugin will generate blending logic here.
    // It reads from a float3 buffer and applies it to a float3 position.
    // --- [PYTHON-MANAGED LOGIC END] ---

    // Apply ONLY the position difference. Normal and Tangent remain from the base mesh.
    output.position += total_diff_position;
    
    rw_buffer[i] = output;
}
// --- END OF FILE 形态anim_standard_delta_v3.hlsl ---