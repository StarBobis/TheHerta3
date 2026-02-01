// --- START OF FILE 形态anim_packed.hlsl ---
// **** ADDITIVE ANIMATION SHADER - PACKED BUFFERS WITH PER-OBJECT CONTROL ****
// Contributors: Zlevir, Assistant
// Version: 5.0 (Final - Packed Buffers + Range Control)

#define MAX_SLOTS 24

struct VertexAttributes {
    float3 position;
    float3 normal;
    float4 tangent;
};

RWStructuredBuffer<VertexAttributes> rw_buffer : register(u5);
StructuredBuffer<VertexAttributes> base : register(t50);
StructuredBuffer<VertexAttributes> shapekeys[MAX_SLOTS] : register(t51); 
StructuredBuffer<int> shapekey_maps[MAX_SLOTS] : register(t75); // 映射图从 t75 开始

Texture1D<float4> IniParams : register(t120);

// --- [PYTHON-MANAGED BLOCK START] ---
// The Blender plugin will dynamically generate all necessary #define statements here.
// --- [PYTHON-MANAGED BLOCK END] ---

[numthreads(16, 1, 1)]
void main(uint3 threadID : SV_DispatchThreadID)
{
    uint i = threadID.x;
    
    VertexAttributes output = rw_buffer[i];
    
    float3 total_diff_position = float3(0.0, 0.0, 0.0);
    float3 total_diff_normal = float3(0.0, 0.0, 0.0);
    float3 total_diff_tangent = float3(0.0, 0.0, 0.0);

    // --- [PYTHON-MANAGED LOGIC START] ---
    // The Blender plugin will dynamically generate the blending logic here.
    // --- [PYTHON-MANAGED LOGIC END] ---

    output.position += total_diff_position;
    output.normal += total_diff_normal;
    output.tangent.xyz += total_diff_tangent;
    
    rw_buffer[i] = output;
}
// --- END OF FILE 形态anim_packed.hlsl ---