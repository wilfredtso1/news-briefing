import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import Img from './Img.tsx'


    
// Component

        function TemplateThumbnail({
            imgId
        }: {
            imgId: string;
        }) {
            return (
                <a className={"DynamicModal_trigger__F5_LZ"}>
                    <div className={"templatePreview_thumbnailContainer__bNsZu"}>
                        <div className={"thumbnail_thumbnail__FoV5w thumbnail_hasShadow__HNc7b"}>
                            <div className={"thumbnail_thumbnailCover__EAEVn"}>
    
                            </div>
                            <Img id={imgId} />
                        </div>
                    </div>
                </a>
            );
        }
    

export default TemplateThumbnail
