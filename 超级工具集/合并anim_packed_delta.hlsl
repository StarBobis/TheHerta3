// --- START OF FILE res/apply_delta.hlsl ---

// **** SINGLE DELTA APPLICATION SHADER - PACKED POSITION-ONLY ****
// Version: 1.0
// Description: Reads a SINGLE packed position delta buffer and applies it to a
//              base vertex buffer. Designed for modular INI files where each
//              variant loads the base model and applies its own unique delta.

struct VertexAttributes {
    float3 position;
    float3 normal;
    float4 tangent;
};

// u5: The base model's vertex buffer, which will be read from and written to.
RWStructuredBuffer<VertexAttributes> rw_buffer : register(u5);

// t51: The packed position-only delta buffer for this specific model variant.
StructuredBuffer<float3> delta_positions : register(t51); 

// t75: The index map corresponding to the packed delta buffer.
StructuredBuffer<int> delta_map : register(t75);

[numthreads(16, 1, 1)]
void main(uint3 threadID : SV_DispatchThreadID)
{
    uint i = threadID.x;
    
    // Find the index into the packed delta buffer.
    // If there's no change for this vertex, the index will be -1.
    int packed_index = delta_map[i];
    
    if (packed_index != -1)
    {
        // Read the base vertex data.
        VertexAttributes output = rw_buffer[i];
        
        // Read the delta and apply it ONLY to the position.
        output.position += delta_positions[packed_index];
        
        // Write the modified result back.
        rw_buffer[i] = output;
    }
}
// --- END OF FILE res/apply_delta.hlsl ---