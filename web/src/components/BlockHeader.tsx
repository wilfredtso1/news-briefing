import React from 'react'
import type { JSX } from 'react/jsx-runtime'



// Component

        function BlockHeader({
            title,
            subtitle
        }: {
            title: string;
            subtitle: string;
        }) {
            return (
                <header className={"blockHeader_blockHeader__4wlg2 blockHeader_layoutMedium__VMyjB"}>
                    <span className={"blockHeader_title__ued0p"}>
                        <h2 className={"blockHeader_title__ued0p"}>
                            {title}
                        </h2>
                    </span>
                    <span className={"blockHeader_subtitle__mqcBA"}>
                        <h3 className={"text_text__cG3pf text_textWeightRegular__lAQvj text_textSizeFootnote__gdfM_"}>
                            {subtitle}
                        </h3>
                    </span>
                </header>
            );
        }
    

export default BlockHeader
