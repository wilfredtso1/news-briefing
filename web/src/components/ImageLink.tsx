import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import Img from './Img.tsx'


    
// Component

        function ImageLink({
            imgId
        }: {
            imgId: string;
        }) {
            return (
                <a>
                    <Img id={imgId} />
                </a>
            );
        }
    

export default ImageLink
